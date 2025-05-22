import sys
import re

def main():
    lines = [line.rstrip('\n') for line in sys.stdin]
    if len(lines) < 2:
        print("error", file=sys.stderr)
        sys.exit(1)
    s, p = lines[0], lines[1]

    if not re.fullmatch(r'[a-z.*]*', p):
        print("error", file=sys.stderr)
        sys.exit(1)
    if p.startswith('*'):
        print("error", file=sys.stderr)
        sys.exit(1)
    if re.search(r'\*{2,}', p):
        print("error", file=sys.stderr)
        sys.exit(1)

    m, n = len(s), len(p)
    dp = [[False]*(n+1) for _ in range(m+1)]
    dp[0][0] = True

    for j in range(1, n+1):
        if p[j-1] == '*' and j >= 2:
            dp[0][j] = dp[0][j-2]

    for i in range(m+1):
        for j in range(1, n+1):
            if p[j-1] == '*':
                dp[i][j] = dp[i][j-2]
                if i > 0 and (p[j-2] == '.' or s[i-1] == p[j-2]):
                    dp[i][j] |= dp[i-1][j]
            else:
                if i > 0 and (p[j-1] == '.' or s[i-1] == p[j-1]):
                    dp[i][j] = dp[i-1][j-1]

    print("true" if dp[m][n] else "false")

if __name__ == "__main__":
    main()