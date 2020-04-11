import os
import sys
import json
import time
#import ptvsd
import random
import asyncio
import logging
import schedule
import datetime
import requests
import threading
import webbrowser
import digital_option_setting as dos

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from pathlib import Path
from pytz import timezone   
from slack import RTMClient
from decimal import Decimal, getcontext
from main_UI import Ui_ApplicationWindow
from iqoptionapi.stable_api import IQ_Option
from fbs_runtime.application_context.PyQt5 import ApplicationContext

# logging.basicConfig(filename=str(Path.home()) + "\\" + "rtc_user_log.log",
#                     filemode='a',
#                     format='%(asctime)s',
#                     datefmt='%H:%M:%S',
#                     level=logging.ERROR)

class DigitalThread(QThread):  
    balance_bet_started = pyqtSignal()
    terminated = pyqtSignal()   
    resume_started = pyqtSignal()
    auth_result = pyqtSignal()
    avoid_time = pyqtSignal()
    exceeded_limit = pyqtSignal()
    restart = pyqtSignal()
    wait_binary_digital = pyqtSignal()
    initial = pyqtSignal(dict)
    stop_digital = pyqtSignal(dict)
    started = pyqtSignal(dict)
    finished = pyqtSignal(dict)
    lower_payout = pyqtSignal(dict)
    achieved_plan = pyqtSignal(dict)
    actives_deleted = pyqtSignal(dict)
    actives_added = pyqtSignal(dict)
    exceeded_martin = pyqtSignal(dict)    
    resume_digital = pyqtSignal(dict)
    resumed_actives_closed = pyqtSignal(dict)
    achieved_target = pyqtSignal(dict)
    errorOccurred = pyqtSignal(object)

    def __init__(self, iqOptionApi, dos, dmdsArray):
        QThread.__init__(self)
        self.iqOptionApi = iqOptionApi
        self.loginId = dos.loginId
        self.env = dos.env
        self.active_items = dos.active_items
        self.daily_limit = dos.daily_limit
        self.isResumed = dos.isResumed
        self.resumed_active_dict = dos.resumed_active_dict
        self.resumed_profit = dos.profit
        self.resumed_currentProfit = dos.currentProfit
        self.amount = 15
        self.cycle = 5
        self.payout = 73
        self.step = 6
        self.target = 100
        self.dmdsArray = dmdsArray
        self.profit = 0    
        self.isBlocked = False
        self.isOpened = False     
        self.hasUpdated = False
        self.open_close = False
        self.count_buyId_dict = {}
        self.actives_dict = {}
        self.actives_dict_types_array = {}
        self.count = 0
        self.currentProfit = 0 
        self.currentBalance = 0 
        self.lock = threading.Lock() 
        self.isRunning = False     
        self.lossCount = 0
        self.lostAmount = 0
        self.markets = ["AUDCAD","AUDUSD","CADCHF","EURAUD","EURCAD",
                        "EURGBP","EURNZD","EURUSD","GBPAUD","GBPCAD",
                        "GBPCHF","GBPUSD","GBPNZD","GBPJPY","NZDUSD",
                        "USDCHF","USDJPY","EURJPY","AUDJPY", "EURUSD-OTC","AUDCAD-OTC","EURGBP-OTC","GBPUSD-OTC",
                        "NZDUSD-OTC","USDCHF-OTC"]                     

    def run(self):
        #ptvsd.debug_this_thread()
        try:           
            for actives in self.active_items:
                if self.isResumed:
                    if bool(self.actives_dict) is False: 
                        self.profit = self.resumed_profit
                        self.currentProfit = self.resumed_currentProfit
                        self.actives_dict = self.resumed_active_dict
                    self.actives_dict_types_array[actives] = []   
                else:
                    asset, payout = self.get_asset_payout(actives)
                    self.actives_dict[asset] = {'loseCount': 0, 'lostAmount': 0, 'isRunning': False, 'payout': payout}
                    self.actives_dict_types_array[asset] = []   

            if self.isResumed is False:
                self.remove_payout()

            schedule.every(10).minutes.do(self.check_hour_update_payout)      

            self.check_hour_update_payout()
            self.signal_initial()   
            self.run_binary()          

            while True:
                schedule.run_pending()
                time.sleep(1) 
        except Exception as e:
            logging.exception(e)
            print(e)

    def get_asset_payout(self, actives):
        if "/" in actives:    
            splitted = actives.split("/")
            asset = splitted[0]
            payout = splitted[1]
            return asset, int(payout)
        else:
            return None, None
                
    def remove_payout(self):
        copy_active_items = self.active_items.copy()
        self.active_items = []      
        for actives in copy_active_items:
            splitted = actives.split("/")
            asset = splitted[0]
            self.active_items.append(asset)

    def get_kst_time_now(self):
        now = datetime.datetime.utcnow()
        
        # change to this when DST is off
        # return now + datetime.timedelta(hours=-8)

        # change to this when DST is on
        return now + datetime.timedelta(hours=-7)

    def run_binary_payouts(self):
        try:
            while True:
                if self.isBlocked is False:
                    commission_data = self.iqOptionApi.get_commission_change("turbo-option")
                    if commission_data != {}:
                        for active_name in commission_data:
                            if commission_data[active_name] != {}:
                                the_min_timestamp = min(commission_data[active_name].keys())
                                commission = commission_data[active_name][the_min_timestamp]
                                profit = ((100-commission) / 100) * 100
                                if active_name in self.actives_dict:   
                                    self.actives_dict[active_name]['payout'] = profit
                                print(str(int(round(profit))),  "% ", str(active_name), str(datetime.datetime.now().replace(microsecond=0)))
                                #Data have been update so need del
                                del self.iqOptionApi.get_commission_change("turbo-option")[active_name][the_min_timestamp]
                time.sleep(2)
        except Exception as e:               
            logging.exception(e)
            print(e)     
            tries = 3
            for i in range(tries):
                try:             
                    while True:
                        if self.isBlocked is False:
                            commission_data = self.iqOptionApi.get_commission_change("turbo-option")
                            if commission_data != {}:
                                for active_name in commission_data:
                                    if commission_data[active_name] != {}:
                                        the_min_timestamp = min(commission_data[active_name].keys())
                                        commission = commission_data[active_name][the_min_timestamp]
                                        profit = ((100-commission) / 100) * 100
                                        if active_name in self.actives_dict: 
                                            self.actives_dict[active_name]['payout'] = profit
                                        print(str(int(round(profit))),  "% ", str(active_name), str(datetime.datetime.now().replace(microsecond=0)))
                                        #Data have been update so need del
                                        del self.iqOptionApi.get_commission_change("turbo-option")[active_name][the_min_timestamp]
                        time.sleep(2)
                except Exception as e:
                    if i < tries - 1: 
                        continue
                    else:
                        print("run_binary_payouts resume")
                        self.resume()   

    def run_binary(self):
        threading.Thread(target=self.run_binary_payouts, daemon=True).start()        
        threading.Thread(target=self.start_loop, daemon=True).start()         
        
    def get_purchase_time(self):      
        try:
            self.lock.acquire()       
            remaning_time = self.iqOptionApi.get_remaning(self.cycle)
            purchase_time = int(remaning_time) - 31
            return purchase_time
        except Exception as e:
            logging.exception(e)
            print(e) 
            return 5
        finally:
            self.lock.release()    

    def start_loop(self):
        try:
            RTMClient.on(event="message", callback=self.receive_tv_alert)  
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.rtm_client = RTMClient(token="xoxp-769064217570-784049552006-830556023280-c15cf3ec64828b47dff9b3845f56a361")
            self.rtm_client.start()      
        except Exception as e:
            logging.exception(e)
            print(e)

    def validate_text(self, text):
        if "/" in text:     
            splitted = text.split("/")
            types = splitted[0]
            actives = splitted[1]
            action = splitted[2]                    
            if action == "BUY":
                return types, actives, "call"
            elif action == "SELL":
                return types, actives, "put"            
        else:
            return None, None, None
    
    def receive_tv_alert(self, **payload):
        try:
            if self.isBlocked is False:
                data = payload['data']
                if (len(data) != 0):
                    if "text" in data:
                        text = data['text']
                        print(text)
                        types, actives, action = self.validate_text(text)
                        if actives != None and action != None:
                            if actives in self.actives_dict:
                                if actives in self.markets:
                                    print(actives, self.isRunning)   
                                    if types == 'BT5':
                                        self.actives_dict_types_array[actives].append(types)         
                                        threading.Thread(target=self.check_purchase_time, args=[types, actives, action], daemon=True).start() 
        except Exception as e:
            logging.exception(e)
            print(e) 

    def check_purchase_time(self, last_in_types, actives, action):   
        try:                           
            purchase_time = self.get_purchase_time()

            if self.isRunning:
                return
            else:
                self.isRunning = True
            
            #if 3 <= purchase_time <= 60:
            if 242 <= purchase_time <= 300:
                self.check_martin_exceeded_and_time(last_in_types, actives, action)               
            else:
                self.actives_dict[actives]['isRunning'] = False
                self.actives_dict_types_array[actives] = []  
                self.isRunning = False
                print("5 too late")
        except Exception as e:
            self.actives_dict[actives]['isRunning'] = False
            self.actives_dict_types_array[actives] = []  
            self.isRunning = False
            logging.exception(e)
            print(e) 

    def round_up_payout_currentPayout(self, actives):
        payoutRounded = int(round(self.payout))
        currentPayoutRounded = int(round(self.actives_dict[actives]['payout']))  
        return payoutRounded, currentPayoutRounded

    def get_korea_local_time(self):
        kst = self.get_kst_time_now()
        hour = kst.strftime('%H')
        minute = kst.strftime('%M')
        return int(hour), int(minute)
 
    def get_payout(self, asset, data):
        try:   
            payout = data[asset]["turbo"]
            return payout * 100
        except Exception as e:
            logging.exception(e)
            print(e)        
            
    def check_hour_update_payout(self):
        hour, _ = self.get_korea_local_time()  
        if hour == 23:         
            allAsset = self.iqOptionApi.get_all_open_time()      
            data = self.iqOptionApi.get_all_profit() 

            for m in self.markets:               
                isOpen = allAsset["turbo"][m]["open"]   
                if isOpen:                                       
                    payout = self.get_payout(m, data) 
                    self.actives_dict[m]['payout'] = payout
                    schedule.clear()

    def check_martin_exceeded_and_time(self, types, actives, action):        
        try:        
            self.apply_martin(types, actives, action)  
            # hour, minute = self.get_korea_local_time()  
            # if hour == 23 or 0 <= hour <= 11:     
            #     if hour == 23 and minute < 30:                    
            #         self.on_error(actives)
            #         self.avoid_time.emit()   
            #         self.isRunning = False
            #     elif hour == 10 or hour == 11:                       
            #         if self.lossCount > 1:
            #             self.apply_martin(types, actives, action)  
            #         else:                       
            #             self.stop()
            #     else:
            #         self.apply_martin(types, actives, action)  
            # else:
            #     self.on_error(actives)
            #     self.isRunning = False
            #     self.avoid_time.emit()     
        except Exception as e:
            logging.exception(e)
            print(e)

    def apply_martin(self, types, actives, action):
        try:
            payout, currentPayout = self.round_up_payout_currentPayout(actives)
        
            if payout <= currentPayout:
                if abs(self.lostAmount) > 0 and self.lossCount <= self.step:
                    self.buy_with_default_martin_setting_binary(self.lostAmount, self.lossCount, actives, action, types)                            
                elif abs(self.lostAmount) > 0 and self.lossCount > self.step:
                    self.check_exceeded_martin(actives)
                    self.actives_dict[actives]['loseCount'] = 0
                    self.actives_dict[actives]['lostAmount'] = 0    
                    self.lossCount = 0
                    self.lostAmount = 0          
                    self.buy_with_default_amount_binary(actives, action, types)                       
                else:                          
                    self.buy_with_default_amount_binary(actives, action, types)                       
            else:               
                self.signal_lower_payout(currentPayout)
                self.on_error(actives)
                self.isRunning = False
        except Exception as e:
            logging.exception(e)
            print(e)

    def buy_binary(self, money, actives, action):          
        try:
            self.lock.acquire()    
            isSuccessful, buyId = self.iqOptionApi.buy(money, actives, action, self.cycle)
            return isSuccessful, str(buyId)
        except Exception as e:
            logging.exception(e)
            print(e)
            self.actives_dict[actives]['isRunning'] = False        
        finally:
            self.lock.release()         

    def check_win(self, types, actives, action, buyId):       
        try:    
            buyId = int(buyId)           
            self.signal_after_bet_started(buyId, actives, action)

            while True:                     
                result = self.get_option_closed(buyId) 
                if result != None:            
                    status = result['msg']['win']
                    if status == 'win':
                        profit = float(result['msg']['win_amount']) - float(result['msg']['sum'])
                    elif status == 'loose':
                        profit = float(result['msg']['sum']) * -1 
                    elif status == 'equal':
                        profit = 0
                    return self.check_win_after(buyId, types, actives, action, profit)    
                time.sleep(1)
        except Exception as e:
            self.actives_dict[actives]['isRunning'] = False
            logging.exception(e)
            print(e)

    def get_option_closed(self, buyId):
        try:
            self.lock.acquire()    
            result = self.iqOptionApi.get_option_closed(buyId) 
            return result
        except Exception as e:
            logging.exception(e)
            print(e)      
        finally:
            self.lock.release() 

    def check_win_after(self, buyId, types, actives, action, profit):        
        try:  
            status = ""

            if profit < 0:
                status = "LOSS"
                self.profit += float(profit)
                self.currentProfit += float(profit)
                print("------------------------------")
                print("loss: ", float(profit), types, actives, self.currentProfit)
                print("------------------------------")
                self.actives_dict[actives]['loseCount'] += 1           
                self.actives_dict[actives]['lostAmount'] = float(profit)  
                self.actives_dict_types_array[actives] = [] 
                self.lossCount += 1
                self.lostAmount = float(profit)        
            elif profit > 0:
                status = "WIN"
                self.profit += float(profit)
                self.currentProfit += float(profit)
                print("------------------------------")
                print("win: ", float(profit), types, actives, self.currentProfit)
                print("------------------------------")
                self.actives_dict[actives]['loseCount'] = 0
                self.actives_dict[actives]['lostAmount'] = 0  
                self.actives_dict_types_array[actives] = []     
                self.lossCount = 0
                self.lostAmount = 0                  
            elif profit == 0:
                status = "TIE"
                print("------------------------------")
                print("tie: ", float(profit), types, actives, self.currentProfit)
                print("------------------------------")
                self.actives_dict_types_array[actives] = []                

            self.signal_after_bet_ended(status)
            
            self.lock.acquire()         
            if self.isBlocked is False:
                if self.profit >= self.target:
                    threading.Thread(target=self.wait_signal_target_achieved, daemon=True).start() 
            self.lock.release()    

            self.actives_dict[actives]['isRunning'] = False 
        except Exception as e:
            self.actives_dict[actives]['isRunning'] = False     
            logging.exception(e)
            print(e)
        finally:
            self.isRunning = False

    def wait_signal_target_achieved(self):
        try:
            self.isBlocked = True
            self.open_close = True   
            self.isCPatternBlocked = True                      
            nowRunning = []

            if self.isOpened:
                while True:
                    if self.isOpened is False:
                        break

            for actives in self.active_items:
                isRunning = self.actives_dict[actives]['isRunning']
                if isRunning:
                    nowRunning.append(actives)          

            if not nowRunning:
                print("empty")         
            else:
                print(nowRunning)
                for actives in nowRunning: 
                    print(actives)              
                    while True: 
                        isRunning = self.actives_dict[actives]['isRunning']
                        if isRunning is False: 
                            break  

            if self.profit >= self.target:
                print('target achieved', self.currentProfit)                         
                self.signal_achieved_target(self.profit)
            else:
                print('target not achieved', self.currentProfit)
                self.isBlocked = False   
                self.open_close = False   
                self.isCPatternBlocked = False   
                self.isRunning = False
        except Exception as e:
            logging.exception(e)              

    def on_error(self, actives):
        self.actives_dict_types_array[actives] = []  
        self.actives_dict[actives]['isRunning'] = False

    def buy_with_default_amount_binary(self, actives, action, types):
        isSuccessful, buyId = self.buy_binary(self.amount, actives, action)
        if isSuccessful and buyId.isdigit():
            self.check_win(types, actives, action, buyId)
        else:
            self.on_error(actives)

    def buy_with_default_scale_binary(self, lostAmount, actives, action, types):
        isSuccessful, buyId = self.buy_binary((abs(lostAmount) * self.scale), actives, action)
        if isSuccessful and buyId.isdigit():
            self.check_win(types, actives, action, buyId)
        else:
            self.on_error(actives)
            self.isRunning = False

    def buy_with_default_martin_setting_binary(self, lostAmount, loseCount, actives, action, types):    
        isSuccessful, buyId = self.buy_binary((abs(lostAmount) * self.dmdsArray[loseCount - 1]), actives, action)
        if isSuccessful and buyId.isdigit():
            self.check_win(types, actives, action, buyId)
        else:
            self.on_error(actives)
  
    def signal_initial(self):
        data = {           
            'isResumed': self.isResumed
        }

        self.initial.emit(data)  

    def signal_exceeded_martin(self, actives):       
        data = {          
            'actives': actives,
            'datetime': str(datetime.datetime.now().replace(microsecond=0))
        }

        self.exceeded_martin.emit(data)

    def signal_actives_deleted(self, actives):       
        data = {          
            'actives': actives,
            'datetime': str(datetime.datetime.now().replace(microsecond=0))
        }

        self.actives_deleted.emit(data)

    def signal_actives_added(self, actives):       
        data = {          
            'actives': actives,
            'datetime': str(datetime.datetime.now().replace(microsecond=0))
        }

        self.actives_added.emit(data)

    def signal_achieved_profit(self, currentProfit):       
        data = {          
            'currentProfit': round(currentProfit, 2),
            'datetime': str(datetime.datetime.now().replace(microsecond=0))
        }

        self.achieved_plan.emit(data)

    def signal_lower_payout(self, currentPayout):       
        data = {          
            'currentPayout': currentPayout,
            'datetime': str(datetime.datetime.now().replace(microsecond=0))
        }

        self.lower_payout.emit(data)

    def signal_after_bet_started(self, buyId, actives, action):
        if action == "call":
            action = "BUY"
        else:
            action = "SELL"

        self.count += 1
        self.count_buyId_dict[buyId] = {'count': self.count}

        data = {
            'count': self.count,
            'actives': actives,
            'action': action,
            'datetime': str(datetime.datetime.now().replace(microsecond=0))
        }

        self.started.emit(data)

    def signal_after_bet_ended(self, status):         
        data = {           
            'profit': self.profit,
            'status': status
        }

        self.finished.emit(data)

    def signal_resumed_actives_closed(self, actives):         
        data = {           
            'actives': actives
        }

        self.resumed_actives_closed.emit(data)

    def signal_achieved_target(self, profit):       
        data = {          
            'profit': round(profit, 2),
            'datetime': str(datetime.datetime.now().replace(microsecond=0))
        }

        self.achieved_target.emit(data)

    def signal_resume(self):         
        data = {           
            'active_items': self.active_items,
            'actives_dict': self.actives_dict,
            'profit': self.profit,
            'currentProfit': self.currentProfit
        }

        self.resume_digital.emit(data)

    def signal_stop_digital(self):         
        data = {           
            'profit': self.profit
        }

        self.stop_digital.emit(data)

    def resume(self):
        try:
            self.resume_started.emit()
            self.isBlocked = True 
            self.open_close = True
            time.sleep(30)  

            if self.isOpened:
                while True:
                    if self.isOpened is False:
                        break
                    time.sleep(1)

            schedule.clear()
            self.rtm_client.stop()   
        except Exception as e:
            logging.exception(e)
            print(e)
        finally:
            self.signal_resume()

    def stop(self):  
        try:          
            self.signal_stop_digital() 
            self.isBlocked = True 
            self.open_close = True       
            time.sleep(30)     

            if self.isOpened:
                while True:
                    if self.isOpened is False:
                        break
                    time.sleep(1)

            current_balance = self.iqOptionApi.get_balance() 
            self.save_user_balance(current_balance)

            schedule.clear()
            self.rtm_client.stop()   
        except Exception as e:
            logging.exception(e)
            print(e)
        finally:
            self.terminated.emit()    
    
    #region DB Connection
    def get_url(self, path):
       #return 'http://localhost:61238/api' + path
       return 'https://rtccanada.azurewebsites.net/api' + path
 
    def save_user_balance(self, balance):        
        try:
            response = self.post_user_balance(balance)
            if response.status_code == 200:
                return True, response.text
            elif response.status_code == 404:
                return False, '404'
            else:
                return False, response.text
        except Exception as e:
            logging.exception(e)
            print(e)
            tries = 3
            for i in range(tries):
                try:
                    response = self.post_user_balance(balance)
                    if response.status_code == 200:
                        return True, response.text
                    elif response.status_code == 404:
                        return False, '404'
                    else:
                        return False, response.text
                except Exception as e:
                    if i < tries - 1: 
                        continue
                    else:
                        return False, e   
                time.sleep(2)

    def post_user_balance(self, balance):
        data = {'email': self.loginId, 'balance': balance, 'env': self.env}
        data_json = json.dumps(data, indent=4, sort_keys=True, default=str)
        headers = {'Content-type': 'application/json'}
        response = requests.post(self.get_url('/request/log-user-balance'), data=data_json, headers=headers)
        return response
    #endregion

class IQOptionLoginThread(QThread):
    authResult = pyqtSignal(object)
    result = pyqtSignal(dict)
    iqoptionLogin = pyqtSignal()
    findAssets = pyqtSignal()
    errorOccurred = pyqtSignal(object)
    minimumBalanceRequired = pyqtSignal()
    authFailed = pyqtSignal()

    def __init__(self, loginId, loginPwd, env):
        QThread.__init__(self)
        self.loginId = loginId
        self.loginPwd = loginPwd
        self.env = env
        self.markets = ["AUDCAD","AUDUSD","CADCHF","EURAUD","EURCAD",
                        "EURGBP","EURNZD","EURUSD","GBPAUD","GBPCAD",
                        "GBPCHF","GBPUSD","GBPNZD","GBPJPY","NZDUSD",
                        "USDCHF","USDJPY","EURJPY","AUDJPY", "EURUSD-OTC","AUDCAD-OTC","EURGBP-OTC","GBPUSD-OTC",
                        "NZDUSD-OTC","USDCHF-OTC"]                   

    def run(self):
        try:        
            #ptvsd.debug_this_thread() 
            self.iqoptionLogin.emit()
            isSuccess, userId = self.verify_user()    
            if isSuccess:
                isPSuccess, msg = self.check_user_paid(userId)
                if isPSuccess:
                    iqOptionApi = IQ_Option(self.loginId, self.loginPwd)
                    check, reason = iqOptionApi.connect()
                    print(check, reason)
                    if check:
                        if self.env == "DEMO":
                            self.env = "PRACTICE"                    
                        iqOptionApi.change_balance(self.env)
                        current_balance = iqOptionApi.get_balance() 

                        if current_balance < 4000:
                            self.minimumBalanceRequired.emit() 
                            return

                        isSSuccess, msg = self.save_user_balance(current_balance)   
                        if isSSuccess:
                            for actives in self.markets:                                
                                text = actives + "/" + "73"         
                                self.signal_after_actives_added(text)
                            self.authResult.emit(iqOptionApi)
                            #self.find_opened_assets(iqOptionApi)
                        else:
                            if msg == '404':                    
                                self.errorOccurred.emit("Your IQ Option account is not registered in our database. Please submit it from our website. \n디베스 웹사이트를 통해 아이큐 옵션 계정이 등록되어 있지 않습니다.")            
                            else:
                                self.errorOccurred.emit("Error occurred. Please try it again. \n오류가 났습니다. 다시 시도하세요.")
                    else:
                        self.authFailed.emit()
                        return
                else:
                    if msg == '"free"':
                        self.errorOccurred.emit("Your free trial has ended. Please purchase the Bot. \n무료 체험판 기한이 만료되었습니다. 유료 구매 후 사용가능합니다.")
                    elif msg == '"expired"':
                        self.errorOccurred.emit("Your monthly subscription has expired. Please extend your subscription. \n월 이용이 만료되었습니다. 재구매 후 사용가능합니다.")
                    else:
                        self.errorOccurred.emit("Error occurred. Please try it again. \n오류가 났습니다. 다시 시도하세요.")
            else:
                if userId == '404':                    
                    self.errorOccurred.emit("Your IQ Option account is not registered in our database. Please submit it from our website. \n디베스 웹사이트를 통해 아이큐 옵션 계정이 등록되어 있지 않습니다.")            
                else:
                    self.errorOccurred.emit("Error occurred. Please try it again. \n오류가 났습니다. 다시 시도하세요.")
        except Exception as e:
            self.errorOccurred.emit(e)
            logging.exception(e)
            print(e)

    def verify_user(self):        
        try:
            response = self.get_user_exists()
            if response.status_code == 200:
                return True, response.text
            elif response.status_code == 404:
                return False, '404'
            else:
                return False, response.text
        except Exception as e:
            logging.exception(e)
            print(e)
            tries = 3
            for i in range(tries):
                try:
                    response = self.get_user_exists()
                    if response.status_code == 200:
                        return True, response.text
                    elif response.status_code == 404:
                        return False, '404'
                    else:
                        return False, response.text
                except Exception as e:
                    if i < tries - 1: 
                        continue
                    else:
                        return False, e   
                time.sleep(2)

    def check_user_paid(self, userId):        
        try:
            response = self.find_purchase_record(userId)
            if response.status_code == 200:
                return True, response.text
            elif response.status_code == 404:
                return False, '404'
            else:
                return False, response.text
        except Exception as e:
            logging.exception(e)
            print(e)
            tries = 3
            for i in range(tries):
                try:
                    response = self.find_purchase_record(userId)
                    if response.status_code == 200:
                        return True, response.text
                    elif response.status_code == 404:
                        return False, '404'
                    else:
                        return False, response.text
                except Exception as e:
                    if i < tries - 1: 
                        continue
                    else:
                        return False, e   
                time.sleep(2)

    def find_opened_assets(self, iqOptionApi):
        self.findAssets.emit()
        canTrade = False
        asset_payout_dict = {}   
        allAsset = iqOptionApi.get_all_open_time()      
        data = iqOptionApi.get_all_profit() 

        for m in self.markets:               
            isOpen = allAsset["turbo"][m]["open"]   
            if isOpen:             
                if len(asset_payout_dict) < 2:
                    canTrade = True        
                    payout = self.get_payout(m, data) 
                    asset_payout_dict[m] = payout            
        if canTrade:
            sorted_list = sorted(asset_payout_dict.items(), key=lambda x: x[1], reverse=True)
            for key, value in sorted_list:   
                text = key + "/" + str(int(round(value)))            
                self.signal_after_actives_added(text)
            self.authResult.emit(iqOptionApi)
        else:
            self.errorOccurred.emit("GBP/AUD 5min trading is closed at the moment. Please try again later. \nGBP/AUD 5분 거래가 현재 닫혀 있습니다. 나중에 다시 시도해 보세요.")

    def get_payout(self, asset, data):
        try:   
            payout = data[asset]["turbo"]
            return payout * 100
        except Exception as e:
            logging.exception(e)
            print(e)        

    def signal_after_actives_added(self, actives):
        data = {
            'actives': actives
        }
        self.result.emit(data)

    def save_user_balance(self, balance):        
        try:
            response = self.post_user_balance(balance)
            if response.status_code == 200:
                return True, response.text
            elif response.status_code == 404:
                return False, '404'
            else:
                return False, response.text
        except Exception as e:
            logging.exception(e)
            print(e)
            tries = 3
            for i in range(tries):
                try:
                    response = self.post_user_balance(balance)
                    if response.status_code == 200:
                        return True, response.text
                    elif response.status_code == 404:
                        return False, '404'
                    else:
                        return False, response.text
                except Exception as e:
                    if i < tries - 1: 
                        continue
                    else:
                        return False, e   
                time.sleep(2)

    def get_url(self, path):
       #return 'http://localhost:61238/api' + path
       return 'https://rtccanada.azurewebsites.net/api' + path

    def get_user_exists(self):
        data = {'email': self.loginId}
        data_json = json.dumps(data, indent=4, sort_keys=True, default=str)
        headers = {'Content-type': 'application/json'}
        response = requests.post(self.get_url('/request/user-exists'), data=data_json, headers=headers)
        return response

    def find_purchase_record(self, userId):
        data = {'email': self.loginId, 'userId': userId}
        data_json = json.dumps(data, indent=4, sort_keys=True, default=str)
        headers = {'Content-type': 'application/json'}
        response = requests.post(self.get_url('/request/user-purchased'), data=data_json, headers=headers)
        return response

    def post_user_balance(self, balance):
        data = {'email': self.loginId, 'balance': balance, 'env': self.env}
        data_json = json.dumps(data, indent=4, sort_keys=True, default=str)
        headers = {'Content-type': 'application/json'}
        response = requests.post(self.get_url('/request/log-user-balance'), data=data_json, headers=headers)
        return response

class PublicInfoThread(QThread):
    publicInfo = pyqtSignal(dict)

    def __init__(self):
        QThread.__init__(self)
        self.version = "2.2"

    def run(self):
        try:            
            isSuccess, response = self.check_version()
            if isSuccess:
                if response['msg'] == self.version:
                    self.signal_public_info(True, self.version)                   
                else:
                    self.signal_public_info(False, self.version)          
        except Exception as e:
            logging.exception(e)
            print(e)

    def signal_public_info(self, isLatest, version):
        data = {           
            'isLatest': isLatest,
            'version': version
        }

        self.publicInfo.emit(data)  

    def check_version(self):        
        try:
            response = self.get_bot_check_info()
            if response.status_code == 200:
                j = json.loads(response.text)
                return True, j
            elif response.status_code == 404:
                return False, '404'
            else:
                return False, response.text
        except Exception as e:
            logging.exception(e)
            print(e)
            return False, e

    def get_bot_check_info(self):
        headers = {'Content-type': 'application/json'}
        response = requests.get('https://rtccanada.azurewebsites.net/api/request/check-version', headers=headers)
        return response

class ApplicationWindow(QMainWindow):
    iqOptionApi = None
    dos = None
  
    def __init__(self):
        super(ApplicationWindow, self).__init__()
        self.ui = Ui_ApplicationWindow()    
        self.ui.setupUi(self)
        self.profit = 0
        self.ui.bulletin.addItem("** 사용방법**  \n아침 출근전(또는 오후 3시) 봇 실행 후 다음날 아침에 봇 끄고 재시작")    
        self.ui.bulletin.addItem("트레이딩 시간대 3:30 PM-3:00 AM (KST) // 최소필요잔액 $4,000 // 일일목표금액 $100 \n")        
        self.ui.bulletin.addItem("** 경고 ** \n이 트레이딩은 직접적인 투자로 원금이 보장되지 않습니다.\n원금 리스크에 대한 책임은 회사와 무관합니다.\n그래도 트레이딩을 시작하시려면 로그인 후 Start 버튼을 눌러주세요.\n")          
        self.ui.bulletin.addItem("** Warning ** \nThis trading is a direct investment and no principal is guaranteed.\nWe are not liable for the loss of principal during/after trading.\nIf you still want to start trading, login and press Start.\n")        
        self.ui.bulletin.item(2).setForeground(Qt.red)
        self.ui.bulletin.item(3).setForeground(Qt.red)
        # Local Time 
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.show_local_time)
        self.timer.start()      
        # Public Info
        self.ui.download.setHidden(True)
        self.public_info_thread = PublicInfoThread()
        self.public_info_thread.publicInfo.connect(self.public_info)        
        self.public_info_thread.start()    
        # Digital      
        #schedule.every(30).minutes.do(self.auto_resume) 
        self.ui.download.clicked.connect(self.download)
        self.ui.login.clicked.connect(self.on_click_login)         
        self.ui.do_start.clicked.connect(self.on_click_do_start)
        self.ui.do_stop.clicked.connect(self.on_click_do_stop)
        self.ui.do_resume.clicked.connect(self.on_click_do_resume)
        self.initial_btn_status()
        self.dmdsArray = []
        self.AssetOpenArray = []    
        self.openedAssetsArray = []
        self.hasExceededLimit = False
        self.isLastSignalInitial = True
        self.isStopping = False
        self.isPastMidnight = False
        self.latestSignal = None
        self.lastSignal = None    
        self.completeName = os.path.join(Path.home(), "dives_auto_email.txt") 

        if os.path.exists(self.completeName):
            f = open(self.completeName, "r") 
            self.ui.lineEdit.setText(f.read())

    def show_local_time(self):
        self.ui.clock.setText("Your Local Time: " + time.strftime('%Y-%m-%d %H:%M:%S'))  

    def download(self):
        webbrowser.open('https://drive.google.com/drive/folders/12cu-XbSCFIlOh7zTCajy-UWUdANlbwEM?usp=sharing')

    def on_click_login(self):
        self.loginId = self.ui.lineEdit.text()
        loginPwd = self.ui.lineEdit_2.text() 
        self.env = self.ui.comboBox.currentText()

        f = open(self.completeName, "w") 
        f.write(self.loginId) 
        f.close() 

        if not self.loginId:
            self.show_error_message("Please enter email address.")
            return
        if not loginPwd:
            self.show_error_message("Please enter password.")
            return        

        self.ui.progressBar.setRange(0, 0)
        self.login_thread = IQOptionLoginThread(self.loginId, loginPwd, self.env)
        self.login_thread.authResult.connect(self.auth_result)
        self.login_thread.result.connect(self.update_do_actives)
        self.login_thread.iqoptionLogin.connect(self.iqoption_login)
        self.login_thread.findAssets.connect(self.find_assets)
        self.login_thread.errorOccurred.connect(self.error_occurred)   
        self.login_thread.minimumBalanceRequired.connect(self.minimum_balance_required)        
        self.login_thread.authFailed.connect(self.auth_failed)
        self.login_thread.start()

    def show_error_message(self, text):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setText(text)
        msg.setWindowTitle("Error")
        msg.exec_()

    def get_balance(self):
        return self.iqOptionApi.get_balance()    

    def show_balance(self, equity):
        self.ui.balance.setText('${:,.2f}'.format(equity))  

    def on_click_do_stop(self):
        self.isStopping = True
        #schedule.clear()
        self.ui.progressBar.setRange(0, 0)   
        threading.Thread(target=self.digital_thread.stop, daemon=True).start()  
       
    def on_click_do_resume(self):
        self.ui.progressBar.setRange(0, 0)   
        threading.Thread(target=self.digital_thread.resume, daemon=True).start()  

    def on_click_do_start(self): 
        if self.check_do_validation() is False: return   
        self.isStopping = False
        self.ui.progressBar.setRange(0, 0)     
        self.reset_do_balance_and_profit()
        self.save_do_all_martin_details()
        self.digital_thread = DigitalThread(self.iqOptionApi, self.dos, self.dmdsArray)
        self.digital_thread.initial.connect(self.on_do_thread_started)
        self.digital_thread.resume_started.connect(self.resume_started)
        self.digital_thread.started.connect(self.add_item)
        self.digital_thread.restart.connect(self.restart)
        self.digital_thread.wait_binary_digital.connect(self.wait_binary_digital)
        self.digital_thread.finished.connect(self.update_do_after_bet)        
        self.digital_thread.stop_digital.connect(self.stop_digital)
        self.digital_thread.resume_digital.connect(self.resume_digital)
        self.digital_thread.avoid_time.connect(self.avoid_time)
        self.digital_thread.exceeded_limit.connect(self.exceeded_limit)        
        self.digital_thread.terminated.connect(self.on_do_thread_terminated)
        self.digital_thread.lower_payout.connect(self.add_payout_low)        
        self.digital_thread.achieved_plan.connect(self.add_achieved_plan)       
        self.digital_thread.actives_deleted.connect(self.show_actives_deleted)       
        self.digital_thread.actives_added.connect(self.show_actives_added)       
        self.digital_thread.auth_result.connect(self.show_auth_result)       
        self.digital_thread.resumed_actives_closed.connect(self.resumed_actives_closed)  
        self.digital_thread.achieved_target.connect(self.add_achieved_target) 
        self.login_thread.errorOccurred.connect(self.error_occurred)
        self.digital_thread.start()                
        self.apply_do_btn_changes(True)   

    def check_do_validation(self):          
        if self.iqOptionApi is not None:           
            # if len(self.openedAssetsArray) <= 0:
            #     self.show_error_message("GBP/AUD 5min trading is closed at the moment. GBP/AUD 5분 거래가 현재 닫혀 있습니다.")
            #     return False           
            # else:
            #     self.ui.bulletin.clear()   
            #     self.dos = dos.DigitalOptionSetting(self.openedAssetsArray, 200, False, None, 0, 0) 
            self.ui.bulletin.clear()   
            self.dos = dos.DigitalOptionSetting(self.loginId, self.env, self.openedAssetsArray, 100, False, None, 0, 0) 
        else:
            self.show_error_message("Please login to IQ Option.")
            return False

    def reset_do_balance_and_profit(self):
        equity = self.get_balance()
        self.show_balance(equity)
        self.ui.profit.setText("$ 0.00")  

    def save_do_all_martin_details(self):
        self.dmdsArray.append(2.3)
        self.dmdsArray.append(2.3)
        self.dmdsArray.append(2.3)
        self.dmdsArray.append(2.3)
        self.dmdsArray.append(2.3)
        self.dmdsArray.append(2.3)

    def initial_btn_status(self):      
        self.ui.do_start.setEnabled(False)
        self.ui.do_stop.setEnabled(False)
        self.ui.do_resume.setEnabled(False)
        self.ui.do_start.setStyleSheet('QPushButton {background-color: gray;}')        
        self.ui.do_stop.setStyleSheet('QPushButton {background-color: gray;}')
        self.ui.do_resume.setStyleSheet('QPushButton {background-color: gray;}')

    def apply_do_btn_changes(self, isStarted):
        if isStarted:
            self.ui.do_start.setEnabled(False)
            self.ui.do_stop.setEnabled(True)
            self.ui.do_start.setStyleSheet('QPushButton {background-color: gray;}')
            self.ui.do_stop.setStyleSheet('QPushButton {background-color: #f37575; color: white;}')
        else:
            self.ui.do_start.setEnabled(True)
            self.ui.do_stop.setEnabled(False)
            self.ui.do_stop.setStyleSheet('QPushButton {background-color: gray;}')
            self.ui.do_start.setStyleSheet('QPushButton {background-color: #56c35f; color: white;}')   
       
    def update_profit(self, profit):    
        self.ui.profit.setText('${:,.2f}'.format(profit))   

    def auto_resume(self):   
        if self.isStopping is False:             
            if self.latestSignal == None or self.lastSignal == None:               
                self.ui.progressBar.setRange(0, 0)   
                threading.Thread(target=self.digital_thread.resume, daemon=True).start()             
            elif self.latestSignal == self.lastSignal:             
                self.ui.progressBar.setRange(0, 0)   
                threading.Thread(target=self.digital_thread.resume, daemon=True).start()
            elif self.latestSignal > self.lastSignal:
                self.lastSignal = self.latestSignal      

    @pyqtSlot()
    def auth_failed(self):
        self.show_error_message("You entered the wrong credentials. Please check that the email/password is correct. \n이메일 또는 비밀번호가 올바르지 않습니다. 다시 시도해주세요.")
        self.ui.loading_msg.setText("")
        self.ui.progressBar.setRange(0, 1)
        self.ui.progressBar.setValue(1) 

    @pyqtSlot(dict)
    def add_achieved_target(self, data): 
        profit = data['profit']
        datetime = data['datetime']  
        text = "$" + str(profit) + " Target Achieved"
        self.ui.bulletin.addItem(text)
        self.update_balance()
        self.on_click_do_stop()

    @pyqtSlot(dict)
    def public_info(self, data):       
        isLatest = data['isLatest']
        version = data['version']
        if isLatest:
            msg = "주중 봇 v." + version + "\n"             
            self.ui.publicInfo.setText(msg)
            self.ui.english.setText("")
        else:
            self.ui.download.setHidden(False)
            self.ui.publicInfo.setText("Please download the latest version. 최신 버전을 다운 받으세요.")   
            self.ui.english.setText("")

    @pyqtSlot(object)
    def auth_result(self, result):
        self.ui.loading_msg.setText("")
        self.iqOptionApi = result   
        equity = self.get_balance()
        self.show_balance(equity)
        self.ui.progressBar.setRange(0, 1)
        self.ui.progressBar.setValue(1)   
        self.apply_do_btn_changes(False)

    @pyqtSlot(object)
    def error_occurred(self, result):        
        self.show_error_message(result)
        self.ui.loading_msg.setText("")
        self.ui.progressBar.setRange(0, 1)
        self.ui.progressBar.setValue(1) 

        self.ui.do_start.setEnabled(False)
        self.ui.do_stop.setEnabled(False)
        self.ui.do_start.setStyleSheet('QPushButton {background-color: gray;}')
        self.ui.do_stop.setStyleSheet('QPushButton {background-color: gray;}')

    @pyqtSlot()
    def resume_started(self):    
        self.ui.loading_msg.setText("Resuming.. wait 30 seconds..")           
        self.ui.do_resume.setEnabled(False)    
        self.ui.do_resume.setStyleSheet('QPushButton {background-color: gray;}')  

    @pyqtSlot()
    def restart(self):    
        self.ui.loading_msg.setText("Daily trade finished.. Closing the bot..")
        text = "Daily trade finished. Restart the bot before 3PM (KST)" 
        self.ui.bulletin.addItem(text)   
        self.isPastMidnight = True
        self.ui.do_start.setEnabled(False)
        self.ui.do_start.setStyleSheet('QPushButton {bafckground-color: gray;}')         
        self.on_click_do_stop()        

    @pyqtSlot(dict)
    def bot_price_balance(self, data):  
        bot_price = int(data['bot_price'])
        current_balance = float(data['current_balance'])
        self.botPrice = bot_price
        self.save_do_all_martin_details()       
        if self.botPrice == 500:
            self.daily_limit = 120
        if self.botPrice == 1000:
            self.daily_limit = 200
        if self.botPrice == 2000:
            if current_balance < 30000:
                self.daily_limit = 400   
            elif current_balance >= 30000:
                self.daily_limit = 600               

    @pyqtSlot()
    def minimum_balance_required(self): 
        self.ui.loading_msg.setText("Minimum balance of $4000 is required for trading.")
        self.ui.progressBar.setRange(0, 1)
        self.ui.progressBar.setValue(1)   

        self.ui.do_start.setEnabled(False)
        self.ui.do_stop.setEnabled(False)
        self.ui.do_start.setStyleSheet('QPushButton {background-color: gray;}')
        self.ui.do_stop.setStyleSheet('QPushButton {background-color: gray;}') 

    @pyqtSlot(dict)
    def stop_digital(self, data):   
        self.profit = data['profit']    
        self.ui.do_resume.setEnabled(False)
        self.ui.do_resume.setStyleSheet('QPushButton {background-color: gray;}') 
        self.ui.loading_msg.setText("Shutting down..  wait 30 seconds.. ")

    @pyqtSlot(dict)
    def resume_digital(self, data):          
        #ptvsd.debug_this_thread()      
        active_items = data['active_items']  
        actives_dict = data['actives_dict']
        self.profit = data['profit']  
        currentProfit = data['currentProfit']  
        self.digital_thread.terminate()
        self.openedAssetsArray = []
        self.ui.loading_msg.setText("")    

        for actives in active_items:
            self.openedAssetsArray.append(actives) 

        for key, value in actives_dict.items():
            actives_dict[key]['isRunning'] = False     

        endedTime = str(datetime.datetime.now().replace(microsecond=0))  
        text = "Resumed the bot: " + endedTime
        self.ui.bulletin.addItem(text)   
        self.ui.do_resume.setEnabled(True)
        self.ui.do_resume.setStyleSheet('QPushButton {background-color: #cbd622; color: white;}')
        self.ui.progressBar.setRange(0, 0)     
        self.dos = dos.DigitalOptionSetting(self.loginId, self.env, self.openedAssetsArray, 100, True, actives_dict, self.profit, currentProfit) 
        self.digital_thread = DigitalThread(self.iqOptionApi, self.dos, self.dmdsArray)
        self.digital_thread.initial.connect(self.on_do_thread_started)
        self.digital_thread.resume_started.connect(self.resume_started)
        self.digital_thread.started.connect(self.add_item)
        self.digital_thread.restart.connect(self.restart)
        self.digital_thread.wait_binary_digital.connect(self.wait_binary_digital)
        self.digital_thread.finished.connect(self.update_do_after_bet)        
        self.digital_thread.stop_digital.connect(self.stop_digital)
        self.digital_thread.resume_digital.connect(self.resume_digital)
        self.digital_thread.avoid_time.connect(self.avoid_time)
        self.digital_thread.exceeded_limit.connect(self.exceeded_limit)        
        self.digital_thread.terminated.connect(self.on_do_thread_terminated)
        self.digital_thread.lower_payout.connect(self.add_payout_low)        
        self.digital_thread.achieved_plan.connect(self.add_achieved_plan)       
        self.digital_thread.actives_deleted.connect(self.show_actives_deleted)       
        self.digital_thread.actives_added.connect(self.show_actives_added)       
        self.digital_thread.auth_result.connect(self.show_auth_result)        
        self.digital_thread.resumed_actives_closed.connect(self.resumed_actives_closed)  
        self.digital_thread.achieved_target.connect(self.add_achieved_target)
        self.login_thread.errorOccurred.connect(self.error_occurred)
        self.digital_thread.start()                
        self.apply_do_btn_changes(True) 

        # schedule.clear()
        # schedule.every(30).minutes.do(self.auto_resume) 

    @pyqtSlot()
    def iqoption_login(self):
        self.ui.loading_msg.setText("Signing in to IQ Option...")

    @pyqtSlot()
    def find_assets(self):
        self.ui.loading_msg.setText("Finding assets...")

    @pyqtSlot()
    def update_balance(self):
        time.sleep(2)
        equity = self.get_balance()
        self.show_balance(equity)

    @pyqtSlot()
    def exceeded_limit(self):    
        self.ui.loading_msg.setText("Exceeded daily limit.")
        text = "Exceeded daily limit. Close the bot and restart from 2 PM (KST)" 
        self.ui.bulletin.addItem(text)         
        self.hasExceededLimit = True
        self.ui.do_start.setEnabled(False)
        self.ui.do_start.setStyleSheet('QPushButton {background-color: gray;}')         
        self.on_click_do_stop()

    @pyqtSlot()
    def wait_binary_digital(self):  
        endedTime = str(datetime.datetime.now().replace(microsecond=0))       
        text = "Payout Low: " + endedTime
        self.ui.bulletin.addItem(text)  
        self.latestSignal = endedTime
        if self.isLastSignalInitial:
            self.lastSignal = endedTime
            self.isLastSignalInitial = False

    @pyqtSlot()
    def avoid_time(self):    
        endedTime = str(datetime.datetime.now().replace(microsecond=0))  
        text = "Avoiding a Fluctuating Market: " + endedTime
        self.ui.bulletin.addItem(text)       
        self.latestSignal = endedTime
        if self.isLastSignalInitial:
            self.lastSignal = endedTime
            self.isLastSignalInitial = False

    @pyqtSlot()
    def show_auth_result(self):   
        endedTime = str(datetime.datetime.now().replace(microsecond=0))
        text = "Bot Reset, Re-Login: " + endedTime
        self.ui.bulletin.addItem(text)     

    @pyqtSlot(dict)
    def show_actives_added(self, data):       
        actives = data['actives']
        datetime = data['datetime']  
        text = "Asset Added: " + datetime + "/" + actives
        self.ui.bulletin.addItem(text)         

    @pyqtSlot(dict)
    def show_actives_deleted(self, data):   
        actives = data['actives']
        datetime = data['datetime']       
        text = "Asset Closed: " + datetime + "/" + actives
        self.ui.bulletin.addItem(text)

    @pyqtSlot(dict)
    def add_achieved_plan(self, data): 
        currentProfit = data['currentProfit']
        datetime = data['datetime']  
        text = "$" + str(currentProfit) + " earned: " + datetime
        self.ui.bulletin.addItem(text)
        self.latestSignal = datetime
        if self.isLastSignalInitial:
            self.lastSignal = datetime
            self.isLastSignalInitial = False

    @pyqtSlot(dict)
    def add_payout_low(self, data):       
        currentPayout = data['currentPayout']
        datetime = data['datetime']       
        text = "Payout Low: " + datetime + "/" + str(currentPayout) + "%"
        self.ui.bulletin.addItem(text)
        self.latestSignal = datetime
        if self.isLastSignalInitial:
            self.lastSignal = datetime
            self.isLastSignalInitial = False

    @pyqtSlot()
    def on_do_thread_terminated(self):
        self.ui.loading_msg.setText("")
        self.ui.progressBar.setRange(0, 1)
        self.ui.progressBar.setValue(1)       
        if self.hasExceededLimit is False:
            self.apply_do_btn_changes(False) 
        self.digital_thread.terminate()
        endedTime = str(datetime.datetime.now().replace(microsecond=0))
        text = str("\n" + "Bot Stopped: " + endedTime)
        self.ui.bulletin.addItem(text)
        self.ui.do_resume.setEnabled(False)
        self.ui.do_resume.setStyleSheet('QPushButton {background-color: gray;}')           
        if self.isPastMidnight or self.hasExceededLimit:
            self.ui.do_start.setEnabled(False)
            self.ui.do_start.setStyleSheet('QPushButton {background-color: gray;}')       
            self.ui.do_stop.setEnabled(False)
            self.ui.do_stop.setStyleSheet('QPushButton {background-color: gray;}')       

    @pyqtSlot(dict)
    def on_do_thread_started(self, data):
        isResumed = data['isResumed']
        self.ui.progressBar.setRange(0, 1)
        self.ui.progressBar.setValue(1)
        if isResumed is False:
            startedTime = str(datetime.datetime.now().replace(microsecond=0))
            text = str("Bot Started: " + startedTime + "\n")
            self.ui.bulletin.addItem(text)
        self.ui.do_resume.setEnabled(True)
        self.ui.do_resume.setStyleSheet('QPushButton {background-color: #cbd622; color: white;}')

    @pyqtSlot(dict)
    def update_do_actives(self, data): 
        actives = data['actives']    
        self.openedAssetsArray.append(actives) 
  
    @pyqtSlot(dict)
    def add_item(self, data):
        count = data['count']
        actives = data['actives']
        action = data['action']
        datetime = data['datetime']
        combined = str(count) + ". " + datetime + " " + actives + "/" + action
        self.ui.bulletin.addItem(combined)
        self.latestSignal = datetime
        if self.isLastSignalInitial:
            self.lastSignal = datetime
            self.isLastSignalInitial = False

    @pyqtSlot(dict)
    def update_do_after_bet(self, data):       
        profit = data['profit']
        status = data['status']
        self.update_status(status)
        self.update_profit(profit)        
        self.update_balance()         

    def update_status(self, status):          
        kor = ""
        if status == "WIN":
            kor = "승"
        elif status == "LOSS":
            kor = "패"
        elif status == "TIE":
            kor = "비김"
        self.ui.bulletin.addItem(status + "/" + kor)

    @pyqtSlot(dict)
    def resumed_actives_closed(self, data):       
        actives = data['actives']
        endedTime = str(datetime.datetime.now().replace(microsecond=0))
        text = str("Asset Closed: " + endedTime + "/" + actives)
        self.ui.bulletin.addItem(text)        
    #end region

if __name__ == '__main__':
    appctxt = ApplicationContext()    
    myWindow = ApplicationWindow()  
    myWindow.show()
    exit_code = appctxt.app.exec_()   
    sys.exit(exit_code)