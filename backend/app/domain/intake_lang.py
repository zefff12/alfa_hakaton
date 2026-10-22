"""Понимание рассказа на английском и китайском.

Вместо отдельных парсеров на каждый язык текст нормализуется в канонические
русские формы («2 million» → «2 млн», «3年» → «3 года», «营业额» → «выручка»),
после чего работает общий, уже проверенный тестами парсер domain/intake.py.
"""
import re

CJK = re.compile(r"[一-鿿]")
LATIN = re.compile(r"[a-zA-Z]")
CYR = re.compile(r"[а-яА-ЯёЁ]")

_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def detect(text: str) -> str:
    if CJK.search(text):
        return "zh"
    latin, cyr = len(LATIN.findall(text)), len(CYR.findall(text))
    return "en" if latin > cyr else "ru"


def _cn_small(s: str) -> int:
    """Китайское число до 9999: 两百 → 200, 三十五 → 35, 十 → 10."""
    total, digit = 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            digit = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            total += (digit or 1) * _CN_UNITS[ch]
            digit = 0
    return total + digit


def _cn_numerals_to_arabic(t: str) -> str:
    # «3百万», «2千万» — арабская цифра с китайским множителем перед 万
    t = re.sub(r"(\d+(?:\.\d+)?)\s*百万", lambda m: f"{float(m.group(1)) * 100:g}万", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*千万", lambda m: f"{float(m.group(1)) * 1000:g}万", t)
    return re.sub(r"[零〇一二两三四五六七八九十百千]+", lambda m: str(_cn_small(m.group(0))), t)


def _cn_money(t: str) -> str:
    def wan(m: re.Match) -> str:
        value = float(m.group(1)) * (1e8 if m.group(2) == "亿" else 1e4)
        return f" {value / 1e6:g} млн " if value >= 1e6 else f" {value / 1e3:g} тыс "
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(万|亿)(?:元|卢布|块)?", wan, t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*千(?:元|卢布|块)?", lambda m: f" {float(m.group(1)):g} тыс ", t)
    return re.sub(r"(\d+(?:\.\d+)?)\s*(元|卢布|块)", r" \1 руб ", t)


ZH_RULES: list[tuple[str, str]] = [
    (r"[，、]", ", "), (r"[。！？]", ". "), (r"；", "; "), (r"：", ": "),
    (r"一年半", " 18 месяцев "), (r"半年", " 6 месяцев "),
    (r"(?:期限|分期|贷款期|借期)\s*(?:为|是)?\s*(?=\d)", " на "),
    (r"年营业额|年收入|年流水|年销售额|年营收", " выручка в год "),
    (r"(?:已有贷款|现有贷款|在贷)\S{0,3}?(?:每月|每个月)?还(?:款|贷)?", " плачу по кредиту "),
    (r"左右|大约|大概|约", " около "),
    (r"(?:经营|开|做|成立|营业)了?\s*(\d+)\s*年", r" работаем \1 года "),
    (r"(?:从|自)?\s*(\d{4})\s*年(?:开始|成立|起|开业)", r" работаем с \1 года "),
    (r"(\d+(?:\.\d+)?)\s*年\s*(?:内)?(?:还清|还完|还款|归还|还)", r" верну за \1 года "),
    (r"(\d+(?:\.\d+)?)\s*(?:个)?月\s*(?:内)?(?:还清|还完|还款|归还|还)", r" верну за \1 месяцев "),
    (r"(?:期限|分期|贷)\s*(\d+(?:\.\d+)?)\s*年", r" на \1 года "),
    (r"(\d+(?:\.\d+)?)\s*年期", r" на \1 года "),
    (r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*年", r" \1 года "),
    (r"(\d+(?:\.\d+)?)\s*个月", r" на \1 месяцев "),
    (r"无抵押|没有抵押|不需要抵押|无需抵押|不要抵押|没抵押", " без залога "),
    (r"抵押物?|担保物", " залог "),
    (r"不急|不着急", " не срочно "),
    (r"急用|很急|着急|尽快|马上|今天|明天|急", " срочно "),
    (r"月供|每月还(?:贷|款)?|每个月还(?:贷|款)?|还贷", " плачу по кредиту "),
    (r"最多(?:能)?(?:还|付)|最多能承受|承受得了|每月最多", " платить могу не больше "),
    (r"营业额|营收|收入|销售额|流水|营业收入|月入|赚", " выручка "),
    (r"支出|开支|费用|成本|花销|开销", " расходы "),
    (r"每个?月|月均|一个月|/月", " в месяц "),
    (r"每年|一年|年度|/年", " в год "),
    (r"再融资|转贷|置换贷款", " рефинансировать "),
    (r"中标|招标|投标|政府合同|政府采购|国家合同", " тендер "),
    (r"资金缺口|周转不开|现金流|发工资|工资", " кассовый разрыв "),
    (r"装修|翻新|改造|维修店", " ремонт "),
    (r"开新店|新门店|分店|新店|扩张|扩大经营|新业务", " открыть новую точку "),
    (r"进货|采购|备货|库存|原材料|商品|货物|囤货", " закупка товара "),
    (r"烤炉|烤箱|设备|机器|机床|生产线|车辆|货车|汽车|咖啡机|冰箱", " оборудование "),
    (r"需要|想贷|想借|想申请|要贷|要借|申请贷款|贷款|借款|借", " нужно "),
    (r"已有贷款|现有贷款|在贷", " текущий кредит "),
    (r"^\s*(没有|无|没|不用|不)\s*[.!]?\s*$", "нет"),
    (r"^\s*(有|是|对|是的|可以)", "да "),
]

EN_RULES: list[tuple[str, str]] = [
    (r"\bone and a half\b", "1.5"), (r"\bhalf a year\b|\bsix months\b", "6 месяцев"),
    (r"\ba year and a half\b", "18 месяцев"),
    (r"\b(?:one|a)\s+million\b", "1 million"), (r"\btwo\b", "2"), (r"\bthree\b", "3"), (r"\bfour\b", "4"),
    (r"\bfive\b", "5"), (r"\bsix\b", "6"), (r"\bseven\b", "7"), (r"\beight\b", "8"), (r"\bnine\b", "9"), (r"\bten\b", "10"),
    (r"(\d),(\d{3})", r"\1\2"), (r"(\d),(\d{3})", r"\1\2"),  # 2,000,000 → 2000000
    (r"(\d)\s*k\b", r"\1 тыс"), (r"\bthousands?\b|\bthous\b", " тыс "),
    (r"(\d)\s*(?:mln|mn|m)\b", r"\1 млн"), (r"\bmillions?\b|\bmln\b", " млн "), (r"\bbillions?\b|\bbn\b", " млрд "),
    (r"\brub(?:les?)?\b|\brur\b", " руб "),
    (r"\babout\b|\baround\b|\broughly\b|\bapproximately\b|~", " около "),
    (r"(?:we(?:'ve| have)? been|been|we are|we're)\s+(?:operating|in business|working|running|trading)\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*years?",
     r" работаем \1 года "),
    (r"\bin business (?:for )?(\d+(?:\.\d+)?)\s*years?", r" работаем \1 года "),
    (r"business is (\d+(?:\.\d+)?)\s*years? old", r" бизнесу \1 года "),
    (r"\bsince (\d{4})\b", r" работаем с \1 года "),
    (r"\b(?:repay|pay (?:it )?back|return it)\s+(?:in|over|within)\s+(\d+(?:\.\d+)?)\s*(years?|months?)", r" верну за \1 \2 "),
    (r"\b(?:for|over|term of|within)\s+(\d+(?:\.\d+)?)\s*(years?|months?)", r" на \1 \2 "),
    (r"\b(?:for|over) a year\b", " на 1 год "),
    (r"\bper month\b|\ba month\b|\bmonthly\b|/month\b|/mo\b", " в месяц "),
    (r"\bper year\b|\ba year\b|\bannual(?:ly)?\b|\byearly\b|/year\b", " в год "),
    (r"\byears?\b", " года "), (r"\bmonths?\b|\bmos?\b", " месяцев "),
    (r"\bno collateral\b|\bwithout collateral\b|\bunsecured\b|\bnothing to pledge\b", " без залога "),
    (r"\bcollateral\b|\bpledge\b|\bsecured by\b", " залог "),
    (r"\bnot urgent\b|\bno rush\b|\bcan wait\b", " не срочно "),
    (r"\burgent(?:ly)?\b|\basap\b|\bas soon as possible\b|\btoday\b|\btomorrow\b", " срочно "),
    (r"\b(?:i )?can(?:not)? pay (?:no more than|at most|up to)|\bat most\b|\bno more than\b|\bnot more than\b|\bmax(?:imum)?\b",
     " платить могу не больше "),
    (r"\b(?:i )?(?:already )?pay\b", " плачу "),
    (r"\b(?:loan|credit|leasing|lease) payments?\b", " платежи по кредиту "),
    (r"\bexisting loans?\b|\bcurrent loans?\b", " текущий кредит "),
    (r"\brevenue\b|\bturnover\b|\bsales\b|\bincome\b|\bwe make\b|\bwe earn\b", " выручка "),
    (r"\bexpenses\b|\bcosts\b|\bspending\b|\boverheads?\b|\bwe spend\b", " расходы "),
    (r"\brefinanc\w*", " рефинансировать "),
    (r"\btender\b|\bgovernment contract\b|\bpublic contract\b|\bstate contract\b", " тендер "),
    (r"\bcash gap\b|\bpayroll\b|\bsalar(?:y|ies)\b|\bwages\b", " кассовый разрыв "),
    (r"\brepairs?\b|\brenovat\w*|\brefurbish\w*", " ремонт "),
    (r"\bnew (?:store|shop|outlet|location|branch|point)\b|\bexpan(?:d|sion)\b|\bopen (?:a )?(?:second|new)\b", " открыть новую точку "),
    (r"\binventory\b|\bstock\b|\bgoods\b|\braw materials?\b|\bpurchas\w*|\bsupplies\b", " закупка товара "),
    (r"\boven\b|\bequipment\b|\bmachine(?:ry)?\b|\bvehicle\b|\btruck\b|\bvan\b|\bcar\b|\bcoffee machine\b|\bproduction line\b",
     " оборудование "),
    (r"\bloans?\b|\bcredit\b", " кредит "),
    (r"\b(?:i |we )?(?:need|want|would like|looking for|borrow|require)\b", " нужно "),
    (r"^\s*(?:no|none|nope|nothing)\b", "нет"),
    (r"^\s*(?:yes|yeah|yep|sure)\b", "да "),
]


def to_canonical(text: str) -> tuple[str, str]:
    """Возвращает (канонический русский текст для парсера, исходный язык)."""
    lang = detect(text)
    if lang == "ru":
        return text, lang
    t = text.lower()
    if lang == "zh":
        t = _cn_numerals_to_arabic(t)
        t = _cn_money(t)
        rules = ZH_RULES
    else:
        rules = EN_RULES
    for pattern, repl in rules:
        t = re.sub(pattern, repl, t)
    return re.sub(r"\s+", " ", t).strip(), lang
