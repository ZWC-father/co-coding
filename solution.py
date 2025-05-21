import sys

def main():
    # 读取输入
    n_line = sys.stdin.readline()
    nums_line = sys.stdin.readline()
    
    # 处理n的输入
    try:
        n = int(n_line.strip())
    except:
        n = 0
    
    # 处理数字序列输入
    if n > 0:
        nums = list(map(int, nums_line.strip().split()))
    else:
        nums = []
    
    # 验证输入数量（调试用）
    # print(f"n={n}, nums={nums}")  # 调试信息
    
    # 排序处理
    sorted_nums = sorted(nums)
    
    # 输出结果
    if n > 0:
        print(' '.join(map(str, sorted_nums)))
    else:
        print('')

if __name__ == "__main__":
    main()