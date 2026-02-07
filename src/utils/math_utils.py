def convert_time_to_seconds(time_str):
    """将 'mm:ss' 格式的时间转换为秒数整数"""
    try:
        if ':' in time_str:
            m, s = map(int, time_str.split(':'))
            return m * 60 + s
        return int(time_str)
    except:
        return 0