
class DigitalOptionSetting(object):

    def __init__(self, loginId, env, active_items, daily_limit, isResumed, resumed_active_dict, profit, currentProfit):
        self.loginId = loginId
        self.env = env
        self.active_items = active_items       
        self.daily_limit = daily_limit
        self.isResumed = isResumed
        self.resumed_active_dict = resumed_active_dict
        self.profit = profit
        self.currentProfit = currentProfit