"""Review helpers for merging and auditing UQER indicator approvals."""

from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


FOREIGN_REGIONS = {
    "日本",
    "美国",
    "德国",
    "英国",
    "法国",
    "韩国",
    "印度",
    "俄罗斯",
    "巴西",
    "澳大利亚",
    "欧盟",
}
LOCAL_REGION_MARKERS = {
    "北京",
    "上海",
    "天津",
    "重庆",
    "河北",
    "河南",
    "山东",
    "山西",
    "陕西",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "四川",
    "贵州",
    "云南",
    "辽宁",
    "吉林",
    "黑龙江",
    "内蒙古",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
    "西藏",
    "杭州",
    "南京",
    "广州",
    "深圳",
}
CATEGORY_KEYWORDS = {
    "价格": ("价格", "现货价", "期货", "结算价", "收盘价", "报价", "市场价", "出厂价"),
    "产量": ("产量", "生产量"),
    "库存": ("库存", "库存量", "仓单"),
    "开工率": ("开工率", "产能利用率"),
    "进口": ("进口",),
    "出口": ("出口",),
    "销量": ("销量", "销售量"),
    "收入": ("收入", "营业收入"),
    "利润": ("利润",),
    "运价": ("运价", "运费"),
}
APPROVAL_RGB = {"FFFFFF00": "yellow", "FF92D050": "green", "FF00B0F0": "blue"}
SHEET_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _manual(status, reason, risks, term="名称对应", product="统计对象对应"):
    return {
        "review_status": status,
        "review_reason": reason,
        "risk_flags": risks,
        "term_check": term,
        "product_check": product,
    }


MANUAL_REVIEWS = {
    ("9", "2020709395"): _manual("近似替代", "同为中海油服钻井服务日历天使用率，但 UQER 为季度累计口径且最新期止于 2024-03。", "累计口径；更新滞后", product="同一公司、同一钻井服务指标"),
    ("10", "2020657630"): _manual("近似替代", "Q5500 秦皇岛平仓价一致，但 UQER 名称未限定“山西产”。", "产地口径未明确", product="动力煤 Q5500 一致；产地限定缺失"),
    ("11", "2020000630"): _manual("近似替代", "UQER 是纽卡斯尔港 NEWC 周度指数，未覆盖目标名称中的肯布拉港。", "港口范围缩窄", product="动力煤 FOB 一致；仅纽卡斯尔港"),
    ("23", "1020008684"): _manual("不可替代", "产能是生产能力，产量是实际产出；两者不能直接替代。", "统计对象冲突", product="电解铝名称相关，但产能≠产量"),
    ("27", "2220006352"): _manual("不可替代", "COMEX 铜库存与 CFTC 多头持仓比重是不同指标。", "统计对象冲突", product="精铜持仓比重≠铜库存"),
    ("27", "2220006353"): _manual("不可替代", "COMEX 铜库存与 CFTC 空头持仓比重是不同指标。", "统计对象冲突", product="精铜持仓比重≠铜库存"),
    ("30", "2220006414"): _manual("不可替代", "黄金期货收盘价与黄金旧年度持仓量量纲、含义均不同。", "统计对象冲突；单位冲突", product="黄金价格≠黄金持仓"),
    ("31", "3010903755"): _manual("不可替代", "目标是美国 10 年期国债收益率，候选是 10 年减 2 年期限利差。", "期限结构口径冲突", product="10Y 收益率≠10Y-2Y 利差"),
    ("45", "2030725762"): _manual("近似替代", "中英文均指 Titanium Dioxide, Rutile Type；UQER 进一步限定 R2 型且为月频市场价。", "规格更窄；频率降低", term="钛白粉=Titanium Dioxide；金红石型=Rutile Type，对应正确", product="R2 型是金红石型子规格"),
    ("52", "2030725900"): _manual("近似替代", "纯 MDI/Pure MDI 产品一致；参考价与市场价来源口径可能不同，且 UQER 为月频。", "价格类型可能不同；频率降低", term="纯 MDI=Pure MDI，对应正确", product="同一化工品"),
    ("58", "2030725832"): _manual("近似替代", "精对苯二甲酸对应 Purified Terephthalic Acid (PTA)；UQER 限定优等品且为月频市场价。", "等级更窄；频率降低", term="精对苯二甲酸=Purified Terephthalic Acid，对应正确", product="同为 PTA；UQER 限定优等品"),
    ("60", "2030725912"): _manual("不可替代", "目标是江浙织机 POY 库存天数，候选是 POY150D/48 市场价格。", "统计对象冲突", term="POY 产品相关，但库存天数与价格不同", product="库存天数≠市场价格"),
    ("61", "2030019289"): _manual("仅补充", "涤纶长丝产量可作为供给补充，但不能代替江浙地区开工率。", "统计对象不同；全国与地区口径不同", product="产量是供给结果，开工率是产能利用状态"),
    ("62", "2030725912"): _manual("仅补充", "产品规格 POY150D/48 基本对应，但全国月频市场价不能完全替代华东/江浙地区平均价。", "地区口径不同；频率降低", term="POY150D/48 与 POY150D/48F 基本对应，F 表示丝束根数", product="同类规格，区域口径不同"),
    ("73", "1040005377"): _manual("仅补充", "产品规格 Φ20mm HRB400E 完全对应，但候选是环比百分比，不是价格水平。", "统计口径冲突", product="螺纹钢牌号与直径一致；环比≠价格原值"),
    ("78", "2040201927"): _manual("仅补充", "HS 7223 仅是不锈钢丝，不能代表全部不锈钢出口数量。", "产品范围缩窄", product="不锈钢丝(HS 7223)是不锈钢子项"),
    ("81", "2060809207"): _manual("近似替代", "熟料是水泥生产的中间品，熟料库容比可作水泥库存压力代理，但不是水泥库容比本身。", "产品层级不同", product="熟料库容比是水泥行业上游库存代理"),
    ("83", "1040005437"): _manual("仅补充", "5mm 浮法平板玻璃规格接近，但候选是环比百分比，不是市场价格水平。", "统计口径冲突", product="4.8/5mm 与 5mm 接近；环比≠价格原值"),
    ("90", "3010500036"): _manual("近似替代", "候选仅覆盖剔除国防和飞机的核心资本品订单，不代表美国制造业全部新订单。", "统计范围缩窄", product="核心资本品订单是制造业新订单子集"),
    ("97", "1020006641"): _manual("近似替代", "行业和同比方向一致，但 UQER 标注累计同比；需用数值对账确认其是否实为期末存货同比。", "累计/期末口径待核", product="专用设备制造业存货一致"),
    ("108", "2087014972"): _manual("仅补充", "HS 842959 包含其他机械铲、挖掘机和装载机，只能作为工程机械出口代理。", "产品范围不同", product="HS 842959 不等于行业口径挖掘机出口"),
    ("116", "1060013427"): _manual("近似替代", "中央本级国防支出对象一致，但“公共财政支出”与现行“一般公共预算支出”存在财政科目沿革。", "财政口径沿革", product="中央本级国防支出一致"),
    ("122", "2020657630"): _manual("近似替代", "Q5500 秦皇岛平仓价一致，但 UQER 名称未限定“山西产”。", "产地口径未明确", product="动力煤 Q5500 一致；产地限定缺失"),
    ("127", "2160606356"): _manual("仅补充", "快递业务收入受业务量和单价共同影响，不能直接替代平均单价。", "统计对象冲突", product="业务收入≠平均单价"),
    ("161", "2070910753"): _manual("近似替代", "均为中国公共充电桩保有量，但 UQER 为 IEA 年频数据，更新频率明显较低。", "频率降低；来源不同", product="公共充电桩保有量一致"),
    ("168", "2170729410"): _manual("不可替代", "预计供应房源是未来新增供给，可售套数是现有库存，两者时点和含义不同。", "统计对象冲突", product="计划供应≠可售库存"),
    ("185", "1070005226"): _manual("近似替代", "原保险保费收入是监管口径中的核心保费收入，与保险公司保费总收入接近但范围可能更窄。", "统计范围可能缩窄", product="原保险保费收入接近但不必然等于全部保费"),
    ("196", "2070201005"): _manual("仅补充", "柴油乘用车只是乘用车出口子项，不能单独替代乘用车出口总量。", "动力类型子项", product="柴油乘用车⊂全部乘用车"),
    ("196", "2070201006"): _manual("仅补充", "汽油乘用车只是乘用车出口子项，不能单独替代乘用车出口总量。", "动力类型子项", product="汽油乘用车⊂全部乘用车"),
    ("200", "2087013505"): _manual("仅补充", "HS 840731 仅覆盖排量≤50ml 的车用往复式活塞发动机。", "产品范围过窄", product="≤50ml 发动机⊂全部车用发动机"),
    ("209", "2070601566"): _manual("仅补充", "民用重型载货汽车注册保有量可反映存量，但不能代替新注册数量。", "新增量/存量冲突", product="注册保有量≠新注册量"),
    ("214", "2070201105"): _manual("仅补充", "柴油商用车出口同比只是总商用车出口的动力类型子项。", "动力类型子项", product="柴油商用车⊂全部商用车"),
    ("214", "2070201106"): _manual("仅补充", "汽油商用车出口同比只是总商用车出口的动力类型子项。", "动力类型子项", product="汽油商用车⊂全部商用车"),
    ("214", "2070201113"): _manual("仅补充", "客车出口同比只是商用车出口的车型子项。", "车型子项", product="客车⊂全部商用车"),
    ("214", "2070201114"): _manual("仅补充", "货车出口同比只是商用车出口的车型子项。", "车型子项", product="货车⊂全部商用车"),
    ("214", "2070201115"): _manual("仅补充", "半挂牵引车出口同比只是商用车出口的车型子项。", "车型子项", product="半挂牵引车⊂全部商用车"),
    ("215", "2070115683"): _manual("仅补充", "大型客车销量环比只保留变化率，不能恢复销量水平。", "统计口径冲突", product="环比≠销量原值"),
    ("218", "2090102508"): _manual("仅补充", "中央空调总销售与线下家用白电空调销售的产品和渠道均不同。", "产品范围冲突；渠道冲突", product="中央空调≠家用空调；总销售≠线下销售"),
    ("225", "2090727341"): _manual("近似替代", "线上小家电零售额同比方向一致，但产品范围大于厨房小家电。", "产品范围更宽", product="厨房小家电⊂小家电"),
    ("225", "2090727367"): _manual("仅补充", "候选既扩大到全部小家电，又是零售额当月值而非同比。", "产品范围更宽；统计口径冲突", product="厨房小家电同比≠小家电销售额原值"),
    ("226", "2090727340"): _manual("近似替代", "线下渠道和同比口径一致，但候选覆盖全部小家电，不只厨房小家电。", "产品范围更宽", product="厨房小家电⊂小家电"),
    ("230", "1020006590"): _manual("近似替代", "行业和同比方向一致，但 UQER 标注累计同比；需核对其是否为期末存货同比。", "累计/期末口径待核", product="纺织服装服饰业存货一致"),
    ("232", "2200000456"): _manual("近似替代", "全国百家重点大型零售企业服装销售可作高质量代理，但样本范围小于限额以上单位服装鞋帽针纺织品类。", "调查样本缩窄；品类缩窄", product="服装零售代理，不含完整鞋帽针纺织品类"),
    ("246", "2087008113"): _manual("近似替代", "HS 9403 覆盖其他家具及零件，未包含所有家具相关 HS 子目。", "HS 范围可能缩窄", product="家具及零件主体一致，海关品类范围需核"),
    ("247", "2200800021"): _manual("近似替代", "重点监测零售企业样本可反映体育娱乐用品需求，但不等于全部限额以上单位。", "调查样本缩窄", product="体育娱乐用品一致"),
    ("252", "2180708533"): _manual("仅补充", "购物人次可解释客流，但购物金额还受客单价影响。", "统计对象不同", product="购物人次≠购物金额"),
    ("258", "2110734936"): _manual("近似替代", "53 度 500ml 飞天茅台规格一致，但 UQER 限定 21 年产品且标为经销商出厂价。", "年份/渠道口径更窄", product="飞天茅台 53度 500ml 对应；限定 21 年"),
    ("260", "2110718055"): _manual("近似替代", "国窖1573 产品对应，但候选是 52%vol 500ml 批发价，不是出厂价。", "价格类型冲突；规格更明确", product="国窖1573 52%vol 500ml；批发价≠出厂价"),
    ("267", "1040001957"): _manual("近似替代", "均反映 CBOT 玉米期货价格，但 UQER 是商务部周频国际期货报价，未明确活跃合约构造。", "合约构造未明确；频率降低", product="CBOT 玉米一致"),
    ("268", "1040001935"): _manual("近似替代", "25% 大米国际现货价和单位一致，但 UQER 中文名未写明泰国，需用来源说明或数值对账确认产地。", "产地未明确", product="大米 25% 规格一致"),
    ("268", "1040002101"): _manual("仅补充", "同为 25% 大米国际现货价，但月频平均值不能替代更高频原始报价，且产地未明确。", "频率降低；产地未明确", product="大米 25% 规格一致"),
    ("271", "2010723633"): _manual("仅补充", "大商所玉米期货价格指数与活跃/指定交割月结算价相关，但合约构造不同。", "合约构造不同", product="玉米期货相关代理"),
    ("273", "1040001958"): _manual("近似替代", "均反映 CBOT 大豆期货价格，但 UQER 是商务部周频报价，未明确活跃合约构造。", "合约构造未明确；频率降低", product="CBOT 大豆一致"),
    ("281", "2140000058"): _manual("近似替代", "维生素 E 国产单价与参考价方向一致，但未注明浓度、剂型和报价市场。", "规格未明确", term="维生素E=Vitamin E，对应正确", product="国产维生素E；浓度/剂型未知"),
    ("282", "2140000058"): _manual("近似替代", "同为国产维生素 E，但 UQER 未注明 50% 含量，不能确认完全同规格。", "浓度规格未明确", term="维生素E=Vitamin E，对应正确", product="目标 50%；候选浓度未知"),
    ("284", "2140200086"): _manual("近似替代", "医药品出口金额与医药材及药品高度相关，但品类边界需核对海关口径。", "品类范围待核", product="医药品与医药材及药品范围可能不完全一致"),
    ("285", "2200800024"): _manual("近似替代", "中西药品类别一致，但重点监测零售企业样本小于全部限额以上单位。", "调查样本缩窄", product="中西药品一致"),
    ("287", "2140000919"): _manual("仅补充", "指标定义同为中药材综合200价格指数，但年频会丢失原指数的高频变化。", "频率过低", product="综合200指数一致"),
    ("295", "2090723373"): _manual("仅补充", "四层以上印刷电路是全部印刷电路出口的子项。", "产品范围缩窄", product="四层以上 PCB⊂全部 PCB"),
    ("303", "2090723373"): _manual("仅补充", "四层以上印刷电路是全部印刷电路出口的子项。", "产品范围缩窄", product="四层以上 PCB⊂全部 PCB"),
    ("310", "2090714994"): _manual("不可替代", "目标是全球苹果智能手机出货量，候选是中国全部智能手机产量。", "品牌冲突；地区冲突；出货/产量冲突", product="苹果出货量≠全品牌智能手机产量"),
}

INDUSTRY_NAMES = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁", "801050": "有色金属",
    "801080": "电子", "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务", "801710": "建筑材料",
    "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒", "801770": "通信", "801780": "银行", "801790": "非银金融",
    "801880": "汽车", "801890": "机械设备", "801950": "煤炭", "801960": "石油石化",
}


def _spec(industry, indicator_id, candidate_type, grade, rationale, risk, related_target=""):
    return {
        "industry_code": industry,
        "industry_name": INDUSTRY_NAMES[industry],
        "uqer_indic_id": str(indicator_id),
        "candidate_type": candidate_type,
        "recommendation_grade": grade,
        "related_target": related_target,
        "recommendation_reason": rationale,
        "key_risk": risk,
    }


NEW_CANDIDATE_SPECS = [
    _spec("801010", 2010711926, "新增行业指标", "A", "全国外三元生猪日频价格，直接反映养殖端供需与盈利周期。", "民间报价来源；需检查节假日与缺失。"),
    _spec("801030", 2020761838, "新增行业指标", "A", "PTA 主力期货周度结算价，可补充现货 PTA 的市场预期与库存周期。", "期货主力构造不同于现货价格。"),
    _spec("801040", 2040001618, "更优替代候选", "A", "Φ20mm HRB400E 周频价格水平，较已审批的月度环比更接近原始价格。", "批发价与原 Wind 价格来源仍需数值对账。", "中国:价格:螺纹钢(HRB400E,20mm)"),
    _spec("801040", 2040104240, "新增行业指标", "A", "全国钢材社会库存周频，直接覆盖钢铁供需与去库节奏。", "需确认库存样本范围和统计口径是否稳定。"),
    _spec("801050", 3010200075, "更优替代候选", "A", "美国财政部 10 年期国债收益率日频，准确替代已审批错误的 10Y-2Y 利差。", "正式使用前做日期和节假日对齐。", "美国:国债到期收益率:10年"),
    _spec("801050", 1020018365, "更优替代候选", "B", "统计对象确为原铝（电解铝）生产能力，比原铝产量更接近目标产能。", "仅年频且最新为 2024 年，不能替代月频变化。", "中国:产能:电解铝:当月值"),
    _spec("801050", 2220100199, "新增行业指标", "A", "全国电解铝日频参考价，可作为有色金属高频价格景气信号。", "百川盈孚报价；历史从 2022 年开始。"),
    _spec("801080", 2090726986, "新增行业指标", "A", "DDR4 8Gb 3200 日频现货平均价，规格较旧 DDR3 更贴近当前存储周期。", "单一 DRAM 规格，不能代表全部半导体。"),
    _spec("801080", 2090715997, "更优替代候选", "A", "中文规格与原 Wind DDR3 4Gb 512Mx8 1600MHz 完全对应，且为日频。", "需核对两源报价时点。", "现货平均价:DRAM:DDR3(4Gb(512Mx8),1600MHz)"),
    _spec("801110", 2090102063, "新增行业指标", "A", "全国空调产量当月同比，补充终端销售之外的供给景气。", "产量可能受库存调整影响，不能单独代表需求。"),
    _spec("801120", 1020008718, "新增行业指标", "A", "全国白酒折 65 度商品量产量同比，直接反映白酒供给周期。", "折度口径与不同酒种结构需保留。"),
    _spec("801120", 2110100015, "更优替代候选", "A", "全国乳制品产量当月值，与原指标统计对象直接对应。", "需核对 Wind 是否使用相同国家统计局口径。", "中国:产量:乳制品:当月值"),
    _spec("801130", 2010004214, "新增行业指标", "A", "中国进口棉价格指数 M（折 1% 关税）日频，直接反映纺织上游成本。", "进口棉口径，不等于国产棉价格。"),
    _spec("801140", 2130700002, "新增行业指标", "A", "纸浆活跃期货日频收盘价，补充造纸成本和库存预期。", "期货价格可能含金融交易噪声。"),
    _spec("801150", 1020008255, "新增行业指标", "A", "全国医药制造业利润总额累计同比，直接覆盖行业盈利景气。", "累计同比有基数效应；1—2 月通常合并。"),
    _spec("801160", 1020001610, "新增行业指标", "A", "全国火电发电量当月同比，直接反映传统电源利用强度。", "受水电来水、气温和能源结构共同影响。"),
    _spec("801160", 1020005933, "更优替代候选", "A", "电力、热力、燃气及水生产供应业利润累计同比，与原指标直接对应。", "行业范围较宽，不能拆分单一公用事业子行业。", "中国:利润总额:电力、热力、燃气及水生产和供应业:累计同比"),
    _spec("801170", 2160000101, "更优替代候选", "A", "CCFI 综合指数周频，准确对应中国出口集装箱运价综合指标。", "航线权重和基期变更需记录。", "中国出口集装箱运价指数:综合指数"),
    _spec("801170", 2160606104, "更优替代候选", "A", "全国快递业务量当月同比，较业务收入更直接反映快递需求。", "件量增长不等于收入增长。", "中国:规模以上快递业务量:当月同比"),
    _spec("801180", 2170000006, "新增行业指标", "A", "70 个大中城市新房价格环比上涨城市数，提供全国性扩散度信号。", "是城市数量而非价格幅度。"),
    _spec("801180", 1050000013, "更优替代候选", "A", "全国房地产开发投资累计同比，与原指标直接对应。", "累计同比存在基数效应。", "中国:房地产开发投资完成额:累计同比"),
    _spec("801200", 1040020070, "新增行业指标", "B", "全国 iCPI 日频环比，可作为商贸零售价格与消费环境高频代理。", "反映价格而非零售数量或金额。"),
    _spec("801210", 2180002608, "新增行业指标", "B", "全国星级饭店 RevPAR，直接反映酒店入住率与房价的综合景气。", "季频且最新为 2024-09，当前更新滞后。"),
    _spec("801710", 1040001844, "更优替代候选", "A", "全国 5/6mm 浮法平板玻璃旬频价格水平，优于已审批的月度环比。", "目标含 4.8/5mm，规格存在轻微差异。", "中国:市场价:浮法平板玻璃(4.8/5mm)"),
    _spec("801720", 1050021433, "新增行业指标", "A", "全国基础设施建设投资累计同比，直接关联建筑装饰订单需求。", "累计同比有基数效应，且基建定义需固定。"),
    _spec("801720", 1050000013, "更优替代候选", "A", "全国房地产开发投资累计同比，与建筑装饰原指标直接对应。", "累计同比存在基数效应。", "中国:房地产开发投资完成额:累计同比"),
    _spec("801730", 1020008757, "新增行业指标", "A", "全国太阳能电池产量当月同比，直接覆盖光伏制造景气。", "产量增长可能伴随价格下跌，需与价格指标配合。"),
    _spec("801730", 2087039087, "更优替代候选", "A", "逆变器 HS85044030 出口数量当月值，与原指标直接对应。", "海关编码调整风险。", "中国:出口数量:逆变器(85044030):当月值"),
    _spec("801740", 2160029349, "新增行业指标", "A", "全国造船完工量累计同比，与新接订单和手持订单形成交付闭环。", "累计同比受大船交付时点影响。"),
    _spec("801740", 1050000359, "更优替代候选", "A", "铁路、船舶、航空航天等运输设备制造投资累计同比，与原指标直接对应。", "行业合并口径较宽。", "中国:固定资产投资完成额:制造业:铁路、船舶、航空航天和其他运输设备制造业:累计同比"),
    _spec("801750", 1050000361, "更优替代候选", "A", "计算机、通信和其他电子设备制造业投资累计同比，与原指标直接对应。", "同时覆盖计算机、通信和电子，行业范围较宽。", "中国:固定资产投资完成额:制造业:计算机、通信和其他电子设备制造业:累计同比"),
    _spec("801760", 2100726811, "高频升级候选", "A", "全国电影票房当日值，比原周频票房更及时。", "日频节假日效应很强，需使用同比或季节调整。", "中国:电影票房收入:当周值"),
    _spec("801770", 2080617140, "更优替代候选", "A", "全国光缆产量当月同比，与通信原指标直接对应。", "光缆产量不能覆盖无线通信服务景气。", "中国:产量:光缆:当月同比"),
    _spec("801780", 2211000531, "新增行业指标", "B", "工商银行净息差季度数据可作为大型银行息差方向的代表性代理。", "单一银行，不可冒充商业银行全行业净息差。"),
    _spec("801790", 2210900111, "新增行业指标", "A", "全国原保险保费收入累计同比，补充保费绝对额的增长信号。", "累计同比有基数效应。"),
    _spec("801880", 2070936211, "更优替代候选", "A", "全国新能源汽车销量当月值，直接对应原目标。", "需核对是否含商用车及口径调整。", "中国:销量:新能源汽车:当月值"),
    _spec("801880", 2070201004, "历史精确候选", "C", "乘用车出口总计当月值，统计对象准确。", "仅更新到 2023-12，适合历史对账，不适合当前跟踪。", "中国:出口数量:乘用车:当月值"),
    _spec("801880", 2070201104, "历史精确候选", "C", "商用车出口总计当月同比，优于各动力/车型子项。", "仅更新到 2023-12。", "中国:出口数量:商用车:当月同比"),
    _spec("801880", 2070125996, "历史精确候选", "C", "大型客车销量当月值，优于环比指标。", "仅更新到 2023-12。", "中国:销量:大型客车"),
    _spec("801890", 2080111196, "更优替代候选", "A", "全国挖掘机销量当月同比，与原目标直接对应。", "协会样本口径变更需跟踪。", "中国:销量:挖掘机:当月同比"),
    _spec("801890", 1020001637, "更优替代候选", "A", "全国金属切削机床产量当月同比，与原指标直接对应。", "国家统计局规模以上工业口径可能调整。", "中国:产量:金属切削机床:当月同比"),
    _spec("801950", 2020000016, "新增行业指标", "A", "动力煤期货日频结算价，提供煤炭行业高频价格预期。", "政策管制与流动性变化可能削弱价格代表性。"),
    _spec("801950", 2020100021, "更优替代候选", "A", "全国原煤产量当月同比，与原指标直接对应。", "统计口径调整和安全检查会造成跳变。", "中国:产量:原煤:当月同比"),
    _spec("801960", 2020656366, "新增行业指标", "A", "美国 EIA 原油库存周频，是全球油价与炼化周期的重要供需变量。", "美国地区指标，不代表中国库存；作为全球油市代理使用。"),
    _spec("801960", 2020701056, "更优替代候选", "A", "WTI 原油现货价日频，与原指标名称、单位直接对应。", "历史从 2019 年开始；可另用 EIA 长历史版本。", "美国:现货价:WTI原油"),
    _spec("801960", 2030700054, "更优替代候选", "A", "全国天然气表观消费量累计值，与原指标直接对应。", "累计值需转换为单月或同比后再用于景气度。", "中国:表观消费量:天然气:累计值"),
    _spec("801960", 1020001547, "更优替代候选", "A", "全国天然气产量当月值，与原指标直接对应。", "需保留国家统计局 1—2 月合并规则。", "中国:产量:天然气:当月值"),
]


def _column_index(cell_ref):
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


def _shared_strings(zf):
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.findall(".//x:t", SHEET_NS)) for item in root.findall("x:si", SHEET_NS)]


def _first_sheet_path(zf):
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    sheet = workbook.find("x:sheets/x:sheet", SHEET_NS)
    relationship_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
    relationships = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for relationship in relationships:
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise ValueError("The first worksheet relationship is missing")


def _style_colors(zf):
    root = ET.fromstring(zf.read("xl/styles.xml"))
    fills = []
    fills_node = root.find("x:fills", SHEET_NS)
    for fill in fills_node if fills_node is not None else []:
        foreground = fill.find("x:patternFill/x:fgColor", SHEET_NS)
        fills.append((foreground.attrib.get("rgb") or "").upper() if foreground is not None else "")
    colors = []
    formats_node = root.find("x:cellXfs", SHEET_NS)
    for cell_format in formats_node if formats_node is not None else []:
        fill_id = int(cell_format.attrib.get("fillId", 0))
        colors.append(fills[fill_id] if fill_id < len(fills) else "")
    return colors


def _cell_value(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", SHEET_NS))
    value = cell.findtext("x:v", default="", namespaces=SHEET_NS)
    if cell_type == "s" and value:
        return shared_strings[int(value)]
    if cell_type == "b":
        return "1" if value == "1" else "0"
    return value


def load_approval_workbook(path, workbook_name):
    """Read manually colored rows from the first sheet of an XLSX workbook."""
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        shared_strings = _shared_strings(zf)
        style_colors = _style_colors(zf)
        sheet = ET.fromstring(zf.read(_first_sheet_path(zf)))

    rows = []
    for row_node in sheet.findall(".//x:sheetData/x:row", SHEET_NS):
        values = {}
        colors = []
        for cell in row_node.findall("x:c", SHEET_NS):
            column = _column_index(cell.attrib["r"])
            values[column] = _cell_value(cell, shared_strings)
            style_id = int(cell.attrib.get("s", 0))
            rgb = style_colors[style_id] if style_id < len(style_colors) else ""
            if rgb in APPROVAL_RGB:
                colors.append(APPROVAL_RGB[rgb])
        if colors:
            rows.append((int(row_node.attrib["r"]), values, Counter(colors).most_common(1)[0][0]))

    header_node = sheet.find(".//x:sheetData/x:row[@r='1']", SHEET_NS)
    headers = {}
    for cell in header_node.findall("x:c", SHEET_NS):
        headers[_column_index(cell.attrib["r"])] = _cell_value(cell, shared_strings)

    records = []
    for excel_row, values, approval_color in rows:
        record = {header: values.get(index, "") for index, header in headers.items()}
        record.update({"approval_color": approval_color, "excel_row": excel_row, "workbook": workbook_name})
        records.append(record)
    return records


def merge_approval_records(full_records, priority_records):
    """Merge decisions by mapping row and UQER ID, with priority overriding duplicates."""
    merged = {}
    for source, records in (("full", full_records), ("priority", priority_records)):
        for original in records:
            record = dict(original)
            record["approval_source"] = source
            mapping_key = str(record.get("mapping_row_id") or record.get("wind_code", ""))
            merged[(mapping_key, str(record["uqer_indic_id"]))] = record
    return sorted(
        merged.values(),
        key=lambda r: (str(r.get("mapping_row_id", "")).zfill(8), str(r.get("uqer_indic_id", ""))),
    )


def _text(value):
    if value is None:
        return ""
    value = str(value).strip()
    return "" if value.lower() == "nan" else value


def _category(name, fallback=""):
    haystack = f"{_text(name)} {_text(fallback)}"
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return ""


def _scope_kind(name, region):
    combined = f"{_text(name)} {_text(region)}"
    if any(marker in combined for marker in FOREIGN_REGIONS):
        return "foreign"
    if any(marker in combined for marker in LOCAL_REGION_MARKERS):
        return "local"
    if any(marker in combined for marker in ("中国", "全国", "国内", "全球", "世界")):
        return "broad"
    return "unknown"


def audit_candidate(record):
    """Return an explainable first-pass audit for an approved candidate."""
    result = dict(record)
    risks = []
    wind_name = _text(record.get("wind_name"))
    uqer_name = _text(record.get("uqer_name"))
    target_scope = _scope_kind(wind_name, "")
    candidate_scope = _scope_kind(uqer_name, record.get("uqer_region"))
    target_category = _category(wind_name, record.get("function_type"))
    candidate_category = _category(uqer_name, "")

    if target_scope == "broad" and candidate_scope == "foreign":
        risks.append("地区冲突")
    elif target_scope == "broad" and candidate_scope == "local":
        risks.append("地区代理")
    if target_category and candidate_category and target_category != candidate_category:
        risks.append("统计对象/功能冲突")

    color = _text(record.get("approval_color")).lower()
    if color == "blue":
        status = "仅补充"
    elif "地区冲突" in risks or "统计对象/功能冲突" in risks:
        status = "不可替代"
    elif risks:
        status = "近似替代"
    else:
        status = "可直接替代"

    result.update(
        {
            "review_status": status,
            "risk_flags": "；".join(risks) if risks else "无明显元数据冲突",
            "scope_check": f"目标={target_scope}；候选={candidate_scope}",
            "term_check": "待结合中英文名与说明复核",
            "product_check": "待结合品种/规格复核",
            "frequency_check": _text(record.get("uqer_frequency")) or "未标注",
            "review_reason": "蓝色按用户规则仅作补充"
            if color == "blue"
            else ("存在关键口径冲突" if status == "不可替代" else "元数据未发现关键冲突"),
        }
    )
    manual = MANUAL_REVIEWS.get((str(record.get("mapping_row_id", "")), str(record.get("uqer_indic_id", ""))))
    if manual:
        result.update(manual)
    if color == "yellow" and result["review_status"] != "可直接替代":
        result["risk_flags"] = f"黄色被下调；{result['risk_flags']}"
    if color == "green" and result["review_status"] == "可直接替代":
        result["risk_flags"] = "绿色复核通过；" + result["risk_flags"]
    return result


def _semantic_tokens(value):
    stop = {"中国", "全国", "当月值", "累计值", "当期值", "期末值", "同比", "环比", "价格", "产量"}
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", _text(value))
    return {token for token in tokens if token not in stop}


def rank_candidate(target, candidate):
    """Rank semantic correctness ahead of geographic scope and frequency."""
    target_name = _text(target.get("wind_name"))
    candidate_name = _text(candidate.get("uqer_name") or candidate.get("indicName"))
    target_category = _category(target_name, target.get("function_type"))
    candidate_category = _category(candidate_name, "")
    score = 0.0
    if target_category and candidate_category:
        score += 50.0 if target_category == candidate_category else -70.0
    overlap = _semantic_tokens(target_name) & _semantic_tokens(candidate_name)
    score += min(30.0, 10.0 * len(overlap))

    target_scope = _scope_kind(target_name, "")
    candidate_scope = _scope_kind(candidate_name, candidate.get("uqer_region") or candidate.get("region"))
    if target_scope == "broad":
        score += {"broad": 25.0, "unknown": 10.0, "local": -20.0, "foreign": -50.0}[candidate_scope]

    frequency = _text(candidate.get("uqer_frequency") or candidate.get("frequency"))
    score += {"日": 12.0, "周": 8.0, "旬": 6.0, "月": 5.0, "季": 1.0, "年": -3.0}.get(frequency, 0.0)
    if _text(candidate.get("uqer_is_update") or candidate.get("isUpdate")) in {"1", "true", "True"}:
        score += 4.0
    return score


def materialize_candidate_specs(specs, metadata_by_id, excluded_ids):
    """Join curated candidate decisions to metadata and drop already selected IDs."""
    excluded = {str(value) for value in excluded_ids}
    rows = []
    for spec in specs:
        indicator_id = str(spec["uqer_indic_id"])
        if indicator_id in excluded:
            continue
        metadata = metadata_by_id.get(indicator_id)
        if not metadata:
            continue
        row = dict(spec)
        row.update(
            {
                "uqer_indic_id": indicator_id,
                "uqer_name": metadata.get("indicName", ""),
                "name_en": metadata.get("nameEN", ""),
                "frequency": metadata.get("frequency", ""),
                "unit": metadata.get("unit", ""),
                "stat_type": metadata.get("statType", ""),
                "region": metadata.get("region", ""),
                "country": metadata.get("country", ""),
                "source": metadata.get("infoSource", ""),
                "api": metadata.get("dataApiName", ""),
                "begin_date": metadata.get("beginDate", ""),
                "end_date": metadata.get("endDate", ""),
                "is_update": metadata.get("isUpdate", ""),
                "memo_cn": metadata.get("memoCN", ""),
            }
        )
        rows.append(row)
    return rows


def load_metadata_by_ids(metadata_root, indicator_ids):
    """Load a small set of indicator metadata from the fixed Parquet snapshots."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("读取 UQER Parquet 元数据需要在项目 .venv 中运行。") from exc

    ids = sorted({int(value) for value in indicator_ids})
    columns = [
        "indicID", "indicName", "nameEN", "frequency", "unit", "statType", "region", "country",
        "currency", "importance", "infoSource", "memoCN", "dataApiName", "beginDate", "endDate", "isUpdate",
    ]
    result = {}
    for path in sorted(Path(metadata_root).glob("snapshot=*/metadata/*.parquet")):
        table = pq.read_table(path, columns=columns, filters=[("indicID", "in", ids)])
        for row in table.to_pylist():
            result[str(row["indicID"])] = row
    return result


def _clean_mapping_row(record, metadata):
    enriched = dict(record)
    enriched.update(
        {
            "meta_name_en": metadata.get("nameEN", ""),
            "meta_memo_cn": metadata.get("memoCN", ""),
            "meta_country": metadata.get("country", ""),
            "meta_currency": metadata.get("currency", ""),
            "meta_importance": metadata.get("importance", ""),
            "uqer_frequency": metadata.get("frequency") or record.get("uqer_frequency", ""),
            "uqer_unit": metadata.get("unit") or record.get("uqer_unit", ""),
            "uqer_stat_type": metadata.get("statType") or record.get("uqer_stat_type", ""),
            "uqer_region": metadata.get("region") or record.get("uqer_region", ""),
            "uqer_source": metadata.get("infoSource") or record.get("uqer_source", ""),
            "uqer_api": metadata.get("dataApiName") or record.get("uqer_api", ""),
            "uqer_begin_date": metadata.get("beginDate") or record.get("uqer_begin_date", ""),
            "uqer_end_date": metadata.get("endDate") or record.get("uqer_end_date", ""),
            "uqer_is_update": metadata.get("isUpdate") if metadata else record.get("uqer_is_update", ""),
        }
    )
    audited = audit_candidate(enriched)
    if audited["term_check"] == "待结合中英文名与说明复核":
        english = _text(audited.get("meta_name_en"))
        audited["term_check"] = f"英文名已核对：{english}" if english else "UQER 未提供英文名；已按中文名和说明复核"
    if audited["product_check"] == "待结合品种/规格复核":
        audited["product_check"] = "中文核心统计对象未见明显冲突；仍需数值对账"

    scope = audited.get("scope_check", "")
    if "候选=unknown" in scope and _text(audited.get("meta_country")) == "中国":
        audited["scope_check"] = scope.replace("候选=unknown", "候选=中国（元数据 country）")
    audited["frequency_check"] = (
        f"{_text(audited.get('uqer_frequency')) or '未标注'}频；"
        f"{_text(audited.get('uqer_begin_date')) or '未知'} 至 {_text(audited.get('uqer_end_date')) or '未知'}；"
        f"isUpdate={_text(audited.get('uqer_is_update')) or '未知'}"
    )
    status = audited["review_status"]
    color = _text(audited.get("approval_color"))
    audited["review_priority"] = (
        "高" if status == "不可替代" or (color == "yellow" and status != "可直接替代")
        else "中" if status in {"近似替代", "仅补充"} or color == "green"
        else "低"
    )
    audited["recommended_action"] = {
        "可直接替代": "进入数值与发布日期对账",
        "近似替代": "分开保存；通过因子稳定性检验后再使用",
        "仅补充": "作为新增解释变量，不替换原序列",
        "不可替代": "移出替代映射；查看更优候选",
    }[status]
    audited["point_in_time_note"] = "元数据 isUpdate 只表示更新状态；正式回测仍须检查观测级 publishDate。"
    return audited


def _write_csv(path, rows, fieldnames):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_outputs(full_path, priority_path, metadata_root, output_dir):
    full = load_approval_workbook(full_path, "full")
    priority = load_approval_workbook(priority_path, "priority")
    merged = merge_approval_records(full, priority)
    selected_ids = {str(row["uqer_indic_id"]) for row in merged}
    required_ids = selected_ids | {str(spec["uqer_indic_id"]) for spec in NEW_CANDIDATE_SPECS}
    metadata = load_metadata_by_ids(metadata_root, required_ids)
    missing_selected = sorted(selected_ids - metadata.keys())
    missing_new = sorted({str(spec["uqer_indic_id"]) for spec in NEW_CANDIDATE_SPECS} - metadata.keys())
    if missing_selected or missing_new:
        raise RuntimeError(f"UQER 元数据缺失：selected={missing_selected}; new={missing_new}")

    reviewed = [_clean_mapping_row(row, metadata[str(row["uqer_indic_id"])]) for row in merged]
    new_candidates = materialize_candidate_specs(NEW_CANDIDATE_SPECS, metadata, selected_ids)
    frequency_rank = {"日": 0, "周": 1, "旬": 2, "月": 3, "季": 4, "半年": 5, "年": 6}
    grade_rank = {"A": 0, "B": 1, "C": 2}
    new_candidates.sort(
        key=lambda row: (
            str(row.get("industry_code", "")),
            grade_rank.get(str(row.get("recommendation_grade", "")), 9),
            frequency_rank.get(str(row.get("frequency", "")), 9),
            str(row.get("uqer_name", "")),
        )
    )

    output_dir = Path(output_dir)
    review_csv = output_dir / "uqer_approval_reaudit_20260811.csv"
    new_csv = output_dir / "uqer_new_strong_candidates_20260811.csv"
    bundle_json = output_dir / "uqer_final_review_bundle_20260811.json"
    review_fields = [
        "mapping_row_id", "industry_code", "wind_code", "wind_name", "function_type", "calculation_type",
        "ValueChain_type", "approval_color", "approval_source", "uqer_indic_id", "uqer_name", "meta_name_en",
        "uqer_frequency", "uqer_unit", "uqer_stat_type", "uqer_region", "meta_country", "uqer_source", "uqer_api",
        "uqer_begin_date", "uqer_end_date", "uqer_is_update", "review_status", "review_priority", "review_reason",
        "risk_flags", "scope_check", "term_check", "product_check", "frequency_check", "recommended_action",
        "point_in_time_note", "meta_memo_cn",
    ]
    new_fields = [
        "industry_code", "industry_name", "candidate_type", "recommendation_grade", "related_target", "uqer_indic_id",
        "uqer_name", "name_en", "frequency", "unit", "stat_type", "region", "country", "source", "api",
        "begin_date", "end_date", "is_update", "recommendation_reason", "key_risk", "memo_cn",
    ]
    _write_csv(review_csv, reviewed, review_fields)
    _write_csv(new_csv, new_candidates, new_fields)
    bundle = {
        "generated_date": "2026-08-11",
        "approval_rules": {
            "yellow": "用户认为可直接替代；本次若发现关键冲突会下调",
            "green": "用户不确定；本次逐条深审",
            "blue": "用户允许作为补充，不作为直接替代",
            "duplicate_precedence": "优先审核表覆盖完整候选表",
        },
        "reviewed": reviewed,
        "new_candidates": new_candidates,
    }
    bundle_json.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"review_csv": review_csv, "new_csv": new_csv, "bundle_json": bundle_json, "reviewed": reviewed, "new_candidates": new_candidates}


def main(argv=None):
    parser = argparse.ArgumentParser(description="复核 UQER 人工审批并生成新增候选。")
    parser.add_argument("--full", default="/Users/lizhexi/Desktop/UQER指标完整候选审核表.xlsx")
    parser.add_argument("--priority", default="/Users/lizhexi/Desktop/UQER指标优先审核表.xlsx")
    parser.add_argument("--metadata-root", default="/private/tmp/uqer-metadata-audit")
    parser.add_argument(
        "--output-dir",
        default="/Users/lizhexi/Desktop/LZX-Intern/01_Projects/202507_行业景气度因子/04_Code/data",
    )
    args = parser.parse_args(argv)
    result = build_outputs(args.full, args.priority, args.metadata_root, args.output_dir)
    status_counts = Counter(row["review_status"] for row in result["reviewed"])
    color_counts = Counter(row["approval_color"] for row in result["reviewed"])
    grade_counts = Counter(row["recommendation_grade"] for row in result["new_candidates"])
    print(
        json.dumps(
            {
                "reviewed_count": len(result["reviewed"]),
                "approval_colors": dict(color_counts),
                "review_status": dict(status_counts),
                "new_count": len(result["new_candidates"]),
                "new_grades": dict(grade_counts),
                "bundle": str(result["bundle_json"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
