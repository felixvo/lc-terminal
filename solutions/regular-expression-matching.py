class Solution:
    def isMatch(self, s: str, p: str) -> bool:
        # from functools import cache
        #
        # @cache
        # def dp(i, j):
        #     if j == len(p):
        #         return i == len(s)
        #
        #     first_match = i < len(s) and p[j] in (s[i], '.')
        #
        #     if j + 1 < len(p) and p[j + 1] == '*':
        #         return dp(i, j + 2) or (first_match and dp(i + 1, j))
        #     else:
        #         return first_match and dp(i + 1, j + 1)
        #
        # return dp(0, 0)
        
        cache = {}

        def dp(i, j):
            if (i,j) in cache:
                return cache[(i, j)]
            if j == len(p):
                return i == len(s)

            first_match = i < len(s) and p[j] in (s[i], '.')
            next_char_is_star = j < len(p) - 1 and p[j+1] == '*'

            if not next_char_is_star and not first_match:
                cache[(i,j)] = False
                return False
            
            if next_char_is_star:
                cache[(i,j)] = dp(i, j+2) or (first_match and dp(i+1, j))
            else:
                cache[(i,j)] = first_match and  dp(i+1, j + 1)
            return cache[(i,j)]


        return dp(0, 0)

