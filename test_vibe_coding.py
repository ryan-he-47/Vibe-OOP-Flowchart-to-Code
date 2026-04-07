import sys

class FourArithmeticCalculator:
    """
    四则计算器（对应流程图中的 N5）
    - MEM: 历史记录（字符串列表，保留最近五次运算）
    """
    def __init__(self):
        self.history: list[str] = []

    def character_filter(self, raw_string: str) -> str:
        """
        字符过滤器（对应 N6）
        从输入的字符串中过滤出数字和四则运算算符，拼接成一个算式
        IN: 原始字符串
        OUT: 算式字符串
        """
        allowed = "0123456789+-*/."
        return "".join(c for c in raw_string if c in allowed)

    def operator(self, formula_string: str) -> str:
        """
        运算器（对应 N7）
        对以字符串形式输入的算式进行计算，输出结果字符串。
        如若输入不合法，则输出“不合法结果，你个傻逼”
        IN: 算式字符串
        OUT: 结果字符串
        """
        if not formula_string or not formula_string.strip():
            return "不合法结果，你个傻逼"
        try:
            # 使用安全的 eval，仅支持数字和四则运算
            result = eval(formula_string, {"__builtins__": {}}, {})
            if isinstance(result, (int, float)):
                return str(result)
            else:
                return "不合法结果，你个傻逼"
        except:
            return "不合法结果，你个傻逼"

    def history_queryer(self, raw_string: str) -> list[str]:
        """
        历史记录查询器（对应 N9）
        当检测到原始字符串中有“hst”字样时，从所属类的成员变量中读取历史记录并输出
        IN: 原始字符串
        OUT: 历史算式列表
        """
        if "hst" in raw_string:
            return self.history.copy()
        return []

    def update_history(self, expr: str, result: str) -> None:
        """
        内部方法：仅在合法运算后更新历史记录（保留最近5条）
        """
        if result != "不合法结果，你个傻逼" and expr:
            self.history.append(f"{expr} = {result}")
            if len(self.history) > 5:
                self.history.pop(0)


def terminal_display(formula: str, result: str, history_list: list[str]) -> None:
    """
    终端输出（对应 N8）
    用花哨的 ASCII 绘画制作一个显示界面
    IN: 算式字符串, 结果字符串, 历史算式列表
    """
    width = 60
    hline = "═" * width

    print("\n╔" + hline + "╗")
    print("║" + "🔢  四则计算器  🔢".center(width) + "║")
    print("╠" + hline + "╣")

    # 显示算式和结果（正常计算时）
    if formula:
        line = f"📝  算式: {formula}"
        print("║" + line.ljust(width)[:width] + "║")
    if result:
        line = f"📟  结果: {result}"
        print("║" + line.ljust(width)[:width] + "║")

    print("╠" + hline + "╣")

    # 显示历史记录（仅当输入包含“hst”时）
    if history_list:
        print("║" + "📜  历史算式列表:".ljust(width) + "║")
        for i, item in enumerate(history_list, 1):
            line = f"   {i}. {item}"
            print("║" + line.ljust(width)[:width] + "║")
    else:
        print("║" + " 💡  提示：输入包含 “hst” 可查询最近 5 次历史记录".ljust(width) + "║")

    print("╚" + hline + "╝")
    print()


def main():
    """
    主程序入口（对应 N4 键盘输入 + 整体流程）
    - 循环读取键盘输入（直到回车）
    - 按照流程图顺序执行：过滤 → 判断是否查询历史 → 计算 → 输出
    """
    calc = FourArithmeticCalculator()

    print("欢迎使用四则计算器！".center(60))
    print("支持 + - * / 小数点混合运算".center(60))
    print("输入包含 “hst” 的任意字符串 → 显示历史记录".center(60))
    print("输入 exit / quit / 退出 → 退出程序".center(60))
    print("=" * 60)

    while True:
        try:
            raw = input("\n👉 请输入: ").strip()

            # 退出命令
            if raw.lower() in ["exit", "quit", "退出"]:
                print("再见！👋")
                break

            # N6：字符过滤器
            formula = calc.character_filter(raw)

            # N9：历史记录查询器
            history_list = calc.history_queryer(raw)

            # 判断是否为历史查询命令
            if "hst" in raw:
                result = ""
                formula = ""  # 不进行计算
            else:
                # N7：运算器
                result = calc.operator(formula)
                # 更新历史（仅合法结果）
                calc.update_history(formula, result)

            # N8：终端花哨 ASCII 输出
            terminal_display(formula, result, history_list)

        except KeyboardInterrupt:
            print("\n\n程序已安全退出。")
            break
        except Exception as e:
            print(f"⚠️  发生意外错误: {e}")


if __name__ == "__main__":
    main()