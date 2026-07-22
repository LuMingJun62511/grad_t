#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反讽数据集生成脚本
基于 PMP + Sarcasm-R1 框架的新版 CoT 结构
支持华为场景，可扩展至其他客户

用法:
    python generate_sarcasm_data.py --category S1 --count 10
    python generate_sarcasm_data.py --all --samples-per-category 10
    python generate_sarcasm_data.py --config custom_config.json
"""

import argparse
import json
import os
import re
import sys
import time
from typing import Optional

# ============================================================
# 一、新版 CoT 模板
# ============================================================

COT_TEMPLATE_SARCASTIC = """【场景/语境】
文本："{text}"
语境：{context}

【一、表面分析】
1.1 字面含义：
{literal_meaning}

1.2 情感极性：
{surface_sentiment}

1.3 背景预设：
{presuppositions}

1.4 伪装判断：
{pretense_analysis}

【二、深层分析】
2.1 真实意图：
{true_intent}

2.2 真实情感：
{true_sentiment}

2.3 情感反转：
{emotion_reversal}

【三、反讽判断】
3.1 判断结果：是反讽

【四、判断依据】
4.1 语言线索：
{linguistic_cues}

4.2 语境线索：
{contextual_cues}

4.3 情感线索：
{emotional_cues}

4.4 伪装机制：
{pretense_mechanism}"""

COT_TEMPLATE_NON_SARCASTIC = """【场景/语境】
文本："{text}"
语境：{context}

【一、表面分析】
1.1 字面含义：
{literal_meaning}

1.2 情感极性：
{surface_sentiment}

1.3 背景预设：
{presuppositions}

1.4 伪装判断：
{pretense_analysis}

【二、深层分析】
2.1 真实意图：
{true_intent}

2.2 真实情感：
{true_sentiment}

2.3 情感反转：
{emotion_reversal}

【三、反讽判断】
3.1 判断结果：不是反讽

【四、判断依据】
4.1 语言线索：
{linguistic_cues}

4.2 语境线索：
{contextual_cues}

4.3 情感线索：
{emotional_cues}

4.4 伪装机制：
{pretense_mechanism}

4.5 反讽要素缺失检查：
{missing_elements}"""

# ============================================================
# 二、20 个分类的定义与生成提示词
# ============================================================

CATEGORY_DEFINITIONS = {
    # ===== 反讽类 =====
    "S1": {
        "name": "直接反话（正话反说）",
        "is_sarcastic": True,
        "description": "字面积极→实际消极。表面用正面词汇夸奖，语境揭示真实的负面评价。",
        "mechanism": "正话反说",
        "pretense_type": "假装褒扬——说话者伪装成一个真心满意的评价者，用正面措辞包装负面事实",
        "emotion_direction": "正→负",
        "generation_guide": """
生成要点：
- 文本前半句建立正面评价（"XX真是太好了""XX绝了""XX做得太棒了"），后半句用事实推翻
- 翻车点要具体——引用一个具体的、可验证的负面事实
- 正面措辞和负面事实之间的落差不靠解释，靠读者自己体会
- 避免直接说"但是"——让矛盾自然暴露
- 华为场景示例：信号/续航/品控/系统流畅度/售后响应等核心体验点
"""
    },

    "S2": {
        "name": "反话正说",
        "is_sarcastic": True,
        "description": "字面消极→实际积极。表面贬低或轻描淡写，实际在赞扬。",
        "mechanism": "反话正说",
        "pretense_type": "假装低调/假装不满——说话者伪装成挑剔者或谦虚者，实则对对象高度认可",
        "emotion_direction": "负→正",
        "generation_guide": """
生成要点：
- 开头用"也就那样""不怎么样""一般般""没什么了不起"等贬抑措辞
- 后续补充的内容实质上是非常正面的——这个正面信息必须足够强以反转前面的贬抑
- 常见句式："XX嘛，也就那样，也就能YY而已"（YY是一个其实很了不起的成就）
- 说话者的"嘴硬身体诚实"是核心笑点
- 华为场景示例：麒麟芯片突破、鸿蒙流畅度、拍照能力等实际有亮点的领域
"""
    },

    "S3": {
        "name": "夸张失当",
        "is_sarcastic": True,
        "description": "夸大到一个理性人不可能相信的程度，夸张本身成为反讽信号。",
        "mechanism": "夸张失当",
        "pretense_type": '假装真诚地使用夸张修辞——伪装成普通的"说话爱用夸张"的人，但夸张程度超出了任何真诚表达的范围',
        "emotion_direction": "正→负（或中性→负）",
        "generation_guide": """
生成要点：
- 夸张要逐层加码——第一层夸张后还要有第二层、第三层更荒谬的夸张
- 夸张对象是与华为产品/服务相关的等待时间、价格、性能差距等
- 时间夸张：冰河期、恐龙时代、地球公转等
- 金钱夸张：卖肾、卖房、贷款等经典梗的变体
- 性能夸张：把正常设备类比为古董设备（"堪比二十年前的XX"）
- 关键：夸张要到了"不可能被当真"的程度才算成功
"""
    },

    "S4": {
        "name": "对比反讽",
        "is_sarcastic": True,
        "description": "通过不匹配的对比来制造讽刺效果，包括降维类比、升维类比、今昔对比。",
        "mechanism": "对比反讽",
        "pretense_type": "假装在进行客观对比——伪装成中立的评测者，但选择的对照组本身就暴露了贬低意图",
        "emotion_direction": "中性→负",
        "generation_guide": """
生成要点：
- 核心技巧：选一个大家都知道很差的参照物，声称目标对象与它"难分伯仲"
- 降维类比：华为旗舰 vs 十年前的老年机/MP4/古董设备
- 升维类比：华为低端产品 vs "爱马仕""奢侈品"（暗讽价格虚高）
- 今昔对比：引用华为过去的承诺 vs 现在的现实
- 对比的参照物选择是第一关键——参照物本身携带的负面含义就是反讽的弹药
"""
    },

    "S5": {
        "name": "假装赞同",
        "is_sarcastic": True,
        "description": '表面同意对方/官方，实则通过"赞同"暴露其荒谬。',
        "mechanism": "假装赞同",
        "pretense_type": "假装被说服——伪装成一个被对方论点说服的人，但'赞同'的方式完全暴露了对方论点的荒谬",
        "emotion_direction": "正→负",
        "generation_guide": """
生成要点：
- 开头用"对对对""你说得对""确实""说得太对了"表达表面认同
- 然后通过补充限定条件、偷换概念、或延伸出荒谬推论来反转
- "偷换概念"是核心技巧——先赞同A，然后把A的含义悄悄替换成B（B是负面的）
- 如："你说得对，'用户至上'——在售后排队时长上确实是至上的"
- 华为场景：偷换"遥遥领先"的含义（从技术领先→价格领先/等待时长领先）
"""
    },

    "S6": {
        "name": "过度礼貌",
        "is_sarcastic": True,
        "description": "用与场景不匹配的极度正式/礼貌程度来表达不满。",
        "mechanism": "过度礼貌",
        "pretense_type": "假装极度恭敬——伪装成一个彬彬有礼到夸张的顾客/用户，礼貌的过度使用本身就是攻击",
        "emotion_direction": "正→负",
        "generation_guide": """
生成要点：
- 使用"尊敬的""劳烦""烦请""万分感谢""铭感五内""有劳""您"等极度正式敬语
- 敬语等级远超正常社交场合所需——售后吐槽用商务公函语气
- 通常在敬语框架中插入一个不可能的时间/条件（"宇宙存续期间""有生之年"）
- 荒诞的时间要求+正式敬语=核心张力
- 华为场景：售后响应慢、系统更新跳票、客服排队等可以用此机制
"""
    },

    "S7": {
        "name": "捧杀",
        "is_sarcastic": True,
        "description": "过度赞美到荒谬的程度，使赞美本身成为攻击。",
        "mechanism": "捧杀",
        "pretense_type": "假装狂热崇拜——伪装成一个极端粉丝/狂热支持者，但赞美的高度已经超出任何真诚崇拜的范围",
        "emotion_direction": "正→负",
        "generation_guide": """
生成要点：
- 赞美要宏大——"人类瑰宝""行业奇迹""文明之光""历史性突破"
- 但赞美的对象要尴尬——是一个其实不值得如此盛赞的细节或缺点
- 将缺点重新定义为优点来赞美，赞美的措辞越宏大，反差越强
- "建议申报联合国非物质文化遗产""建议写入教科书""建议立碑纪念"等拔高句式
- 华为场景：捧杀余承东演讲艺术、过度拔高某次OTA更新的意义、把降价解释为慈善
"""
    },

    "S8": {
        "name": "引用反讽",
        "is_sarcastic": True,
        "description": "引用对方原话、品牌slogan、名言等，在新语境下使其含义翻转。",
        "mechanism": "引用反讽",
        "pretense_type": "假装在认真引用——伪装成尊重原话的引用者，但引用的语境完全消解了原话的含义",
        "emotion_direction": "中性→负",
        "generation_guide": """
生成要点：
- 引用的对象：华为slogan（"遥遥领先""用户至上""中华有为""构建万物互联的智能世界"）、
  余承东名言、任正非名言
- 引述后不要直接否定，而是用具体经历/事实来让引语的含义自然崩塌
- "'XXXX'——这是华为说的。然后我等了三个小时。"让读者自己完成讽刺
- 破折号和引号是重要标记
- 华为场景：引用品牌口号后用真实体验打脸；引用余承东的"本月更新"然后用实际跳票打脸
"""
    },

    "S9": {
        "name": "反问反讽",
        "is_sarcastic": True,
        "description": "用反问句包装反转意图，答案已在问中。",
        "mechanism": "反问反讽",
        "pretense_type": "假装真诚地提问——伪装成在寻求确认或表达疑问，但问题的答案已经内置于问题中且与表面相反",
        "emotion_direction": "正→负",
        "generation_guide": """
生成要点：
- 连续反问是最有效的——两个到三个反问形成节奏和递进
- 反问的答案对读者来说显而易见（且与字面相反）
- "难道……吗？""不会真有人觉得……吧？""这要是算……那我岂不是……？"
- "不会吧不会吧"是中文互联网经典的反讽句式，可以使用
- 最后一个反问往往是高潮——揭示最荒谬的点
- 华为场景：质疑价格合理性、质疑宣传真实性、质疑"自研"含量
"""
    },

    "S10": {
        "name": "自嘲反讽",
        "is_sarcastic": True,
        "description": "表面拿自己开刀，实则矛头指向外部。区分于真诚自嘲：自嘲反讽实际上在讽刺外部对象。",
        "mechanism": "自嘲反讽",
        "pretense_type": "假装自我批评——伪装成在反省自己，但每一条'自我批评'都在反向指控外部对象（产品/品牌/服务）",
        "emotion_direction": "正→负",
        "generation_guide": """
生成要点：
- 核心句式："是我太XX了""怪我""我活该""是我格局小了""是我不够XX"
- 每条自我归因都要配一个外部原因——通过"自我批评"把矛头自然引向外部
- 结尾往往有一个升华式自嘲（"是我人生的错"），荒诞程度标记了反讽姿态
- 与真诚自嘲的关键区别：真诚自嘲中，说话者真的认为自己有问题；自嘲反讽中，说话者通过自嘲来让对方的问题显形
- 华为场景：买了产品发现被坑→"怪我有眼无珠"；价格太高→"怪我太穷"
"""
    },

    # ===== 非反讽类 =====
    "N1": {
        "name": "真诚夸张",
        "is_sarcastic": False,
        "description": "使用了夸张修辞，但真心实意，没有反转意图。情感方向与表达一致。",
        "mechanism": "真诚夸张（非反讽）",
        "why_confusable": "与S3（夸张失当）共享了夸张修辞手段，但情感方向和表达方向一致，无反转、无伪装。",
        "generation_guide": """
生成要点：
- 夸张程度可以很高（"好吃到哭了""激动得跳起来""从沙发上跳了起来"）
- 关键：提供一个具体的行为证据（"真的睡着了""截图都截不到"）来增强真诚度
- 全文情感方向一致——从头到尾在正面表达或在负面表达，没有反转
- 如果是在评价一个被普遍认为不错的华为产品/功能，内容正面，无负面暗示
- 与S3的区别：S3会在夸张中暗示荒谬从而否定，N1用夸张来强化真实的肯定
"""
    },

    "N2": {
        "name": "真诚赞美",
        "is_sarcastic": False,
        "description": "发自内心的夸奖。语气可能热烈但措辞克制，情感方向一致，无伪装。",
        "mechanism": "真诚赞美（非反讽）",
        "why_confusable": "与S1（正话反说）和S7（捧杀）共享了正面措辞的模板，但无反转意图，赞美的框架与对象的实际品质匹配。",
        "generation_guide": """
生成要点：
- 与S1的关键区别：S1的正面措辞后面会有一个"翻车点"，N2没有
- 与S7的关键区别：S7的赞美是拔高到荒谬高度的，N2的赞美是适度的或者高度与对象品质匹配的
- 提供具体的论据："用了一年多"的时间跨度、"多设备流转"的具体功能名
- 可以承认不足（"你要说没有缺点那是假的"）但不因此反转总体正面评价
- "有一说一""不得不承认""不是吹的"等口语化前缀是真诚正名的常见标记（但也能在反讽中出现——关键看后续是否有反转）
"""
    },

    "N3": {
        "name": "直接批评/吐槽",
        "is_sarcastic": False,
        "description": "直接表达不满，没有语义反转。与S1的核心区别：S1绕弯骂，N3直接骂。",
        "mechanism": "直接批评（非反讽）",
        "why_confusable": '与S1共享了负面评价的意图，但表达方式完全不同——N3是直接陈述不满，S1是用正面措辞包装不满。两者在"情感反转"上有关键差别：N3无情感反转。',
        "generation_guide": """
生成要点：
- 直接使用负面词汇，不包装——"垃圾""坑人""割韭菜""服了""太差了"
- 直接提问或质问——"凭什么？""为什么？""这合理吗？"
- 可以列举具体的事实和数字作为不满的证据
- 与S1的关键区别：如果文本把"差"说成"好"，是S1；如果文本直接说"差"，是N3
- 华为场景：批评定价、品控、系统广告、售后效率——但都用直接措辞而非反转措辞
"""
    },

    "N4": {
        "name": "幽默/段子",
        "is_sarcastic": False,
        "description": "纯粹搞笑或段子式的幽默创作。有反转和笑点，但反转是幽默结构而非语义反转（批评意图）。攻击性极低。",
        "mechanism": "幽默段子（非反讽）",
        "why_confusable": '与S4（对比反讽）和S10（自嘲反讽）共享了"转折/反差"的结构，但幽默段子的转折服务于笑点而非服务于批评。攻击性低+对象无害=段子≠反讽。',
        "generation_guide": """
生成要点：
- 采用段子/脱口秀的结构：铺垫→转折→包袱
- 不要有明显的批评对象——调侃的是"命名规则""营销套路"等无害特点而非产品品质
- 可以用对话体、教程体、清单体等幽默形式
- 如果段子中有"批评"，这个批评应该是轻松的、在圈内被普遍接受的调侃
- 与S4的关键区别：S4的类比有明确的贬低对象，N4的段子纯粹为了好笑
"""
    },

    "N5": {
        "name": "中式自谦",
        "is_sarcastic": False,
        "description": "中国文化中的自谦表达——字面与意图不一致，但这是社交礼貌习惯而非语义反转。",
        "mechanism": "中式自谦（非反讽）",
        "why_confusable": '与S2（反话正说）共享了"表面贬低实际肯定"的结构，但动机完全不同——S2是修辞策略（通过假装谦虚来表达反讽肯定），N5是社交礼仪（通过谦虚来获得社会好感）。',
        "generation_guide": """
生成要点：
- 使用经典的中式谦辞："哪里哪里""不敢当""献丑了""也就那样""随便弄的"
- 说话者的意图是遵守谦虚的社会规范，而非通过谦虚来进行修辞表达
- 常见的场景：被表扬后的回应、公开表态、自评
- 与S2的关键区别：判断标准是"说话者是否在通过谦虚来表达另一种修辞意图"——S2的回答是"是"，N5的回答是"否"
- 如果文本可以自然地读作"一个谦虚的人在谦虚"，而非"一个骄傲的人在假装谦虚"，就是N5
"""
    },

    "N6": {
        "name": "网络流行语/梗",
        "is_sarcastic": False,
        "description": "用网络流行语、模因（meme）进行表达——可能包含夸张或反转，但梗的使用本身不等于反讽。",
        "mechanism": "网络梗（非反讽）",
        "why_confusable": '与S8（引用反讽）共享了"引用"的行为，但梗的引用是为了融入社群话语而非为了反转语义进行攻击。',
        "generation_guide": """
生成要点：
- 包含多个知名网络梗或流行语（"遥遥领先"作为梗而非讽刺对象、"这很华为""年轻人的第一台XX"）
- 梗的使用方式是融入和参与，而非劫持和反转
- 如果有自我标注（"开个玩笑""玩梗而已"）更确认非反讽
- 与S8的关键区别：S8引用梗是为了劫持其含义，N6引用梗是为了参与玩梗
- 梗在文本中的功能是建立共鸣而非传达批评
"""
    },

    "N7": {
        "name": "情绪宣泄",
        "is_sarcastic": False,
        "description": "情绪上头的直接宣泄——可能用词夸张但表达方向与真实情绪一致，无包装无反转。",
        "mechanism": "情绪宣泄（非反讽）",
        "why_confusable": "与S3（夸张失当）共享了夸张修辞，但情绪宣泄的夸张是情绪的自然倾斜（无控制），反讽夸张是精心的修辞设计（有控制）。",
        "generation_guide": """
生成要点：
- 标志性的情绪爆发标记：连续叹号、重复（"烦死了烦死了烦死了"）、啊啊啊啊
- 直接喊话、直接指控、直接诅咒——所有的方向都与真实情绪一致
- 没有"正面措辞包装负面情绪"——愤怒就是愤怒的外显
- 与S3的区别：S3的情绪是被修辞包装过的（"我排队排了一个冰河期"），N7的情绪是没有包装的（"我等了三个月还没消息我要疯了！！！"）
- 与S10的区别：S10有"是我太XX了"的自嘲框架，N7没有
"""
    },

    "N8": {
        "name": "委婉表达",
        "is_sarcastic": False,
        "description": '用温和/间接的方式表达批评——有"绕弯"但没有"说反话"。礼貌是出于面子管理而非讽刺。',
        "mechanism": "委婉表达（非反讽）",
        "why_confusable": '与S6（过度礼貌）共享了"间接表达"的结构，但委婉表达的礼貌程度与场景匹配（虽然偏低），过度礼貌的礼貌程度远超场景所需以制造讽刺。',
        "generation_guide": """
生成要点：
- 使用典型的委婉措辞："可能需要一些时间""还有一些完善空间""挺有想法的""从某种角度来说"
- 将尖锐的批评温和化——不是反转语义，而是降低批评的攻击性
- 常见场景：公关/客服话术、媒体评价、同事间提建议
- 与S6的关键区别：看礼貌程度与场景的匹配度。如果礼貌程度合理→N8；如果礼貌程度夸张到荒谬→S6
- "不是没有问题"→N8；"麻烦您在宇宙存续期间回复一下"→S6
"""
    },

    "N9": {
        "name": "有保留的赞同",
        "is_sarcastic": False,
        "description": '真心觉得还行，但措辞保守——"还行""凑合""不差"。容易因措辞简略而被误判为"正话反说"。',
        "mechanism": "有保留的赞同（非反讽）",
        "why_confusable": '与S1（正话反说）和S2（反话正说）共享了简略评价的形式，但N9的评价框架与评价内容匹配——说"还行"是因为真的只达到了"还行"的水平，不是因为差到只能用"还行"来反讽。',
        "generation_guide": """
生成要点：
- 核心是"评价的措辞保守程度"与"对象的实际水平"之间的关系
- 如果对象真的只是"还行"，说"还行"就是诚实评价→N9
- 如果对象显然很差却说"还行"，那就是S1（正话反说）
- 如果对象显然很好却说"还行"，那就是S2（反话正说）
- 提供限定条件和分级评价（"白天可以，夜景一般""放在这个价位算不错"）可以增强真诚度
- 分场景、分参照系的精细化评价往往是真诚的——反讽倾向于笼统评价
"""
    },

    "N10": {
        "name": "情境矛盾叙述",
        "is_sarcastic": False,
        "description": "描述真实的矛盾/反讽情境——情境本身是反讽的，但说话者只是在陈述事实而非通过语言制造反讽。",
        "mechanism": "情境矛盾叙述（非反讽）",
        "why_confusable": '与S4（对比反讽）和S8（引用反讽）共享了"矛盾/对比"结构，但N10的矛盾是客观情境而非说话者的修辞构造。',
        "generation_guide": """
生成要点：
- 这是最难判断的一类：情境本身是"讽刺的"（ironic in situation），但说话者的语言行为是"叙述"而非"讽刺"
- 关键区分：看矛盾是"被陈述的"（N10）还是"被制造的"（S4/S8）
- 如果说话者是在分享一个令人无奈的巧合或矛盾经历→N10
- 如果说话者是在利用修辞手法制造矛盾来攻击对象→S4/S8
- 自我反思的标记（"仔细想想""说真的很讽刺""生活就是这么矛盾"）降低反讽可能性
- 华为场景：制裁反而促进研发、吹过的牛居然实现了、被骂最多的品牌自己也在用
"""
    },
}

# ============================================================
# 三、华为场景素材库
# ============================================================

HUAWEI_ENTITIES = {
    # ================================================================
    # products — 按 业务线 > 品类 组织 (叶子节点是具体产品/名字)
    # ================================================================
    "products": [
        # ----- ToC: 手机 -----
        # Mate 系列
        "Mate 60", "Mate 60 Pro", "Mate 60 Pro+", "Mate 60 RS 非凡大师",
        "Mate 70", "Mate 70 Pro", "Mate 70 Pro+", "Mate 70 RS 非凡大师",
        "Mate 80", "Mate 80 Pro", "Mate 80 Pro Max", "Mate 80 RS 非凡大师",
        "Mate 80 GTS",
        # 折叠屏
        "Mate X3", "Mate X5", "Mate XT", "Mate XT 非凡大师",
        "Mate X7", "Pura X2",
        # Pura 系列
        "Pura 70", "Pura 70 Pro", "Pura 70 Ultra",
        "Pura 80", "Pura 80 Ultra",
        "Pura 90", "Pura 90 Pro", "Pura 90 Pro Max", "Pura 90 Ultra",
        "Pura 90s",
        # nova 系列
        "nova 13", "nova 14", "nova Flip",
        # 畅享系列
        "畅享70",

        # ----- ToC: PC / 平板 -----
        "MateBook X Pro", "MateBook 16", "MateBook 14", "MateBook D 系列",
        "MatePad Pro", "MatePad Air", "MatePad Pro Max", "MatePad SE",
        "鸿蒙PC",

        # ----- ToC: 穿戴 -----
        "华为Watch GT 5", "华为Watch GT 6", "华为Watch Ultimate",
        "华为Watch D2", "华为手环Band 9", "华为手环Band 10",
        "华为智能眼镜",

        # ----- ToC: 音频 -----
        "FreeBuds Pro 4", "FreeBuds Pro 5", "FreeClip",
        "Sound Joy 智能音箱", "Sound X 智能音箱",

        # ----- ToC: 智慧屏 / 路由 / 全屋智能 -----
        "华为智慧屏 Vision", "华为智慧屏",
        "凌霄路由器", "华为智能门锁",
        "华为全屋智能",

        # ----- ToC: 鸿蒙生态 -----
        "鸿蒙OS", "鸿蒙NEXT", "鸿蒙4.0", "鸿蒙5.0", "鸿蒙6.0",
        "鸿蒙系统", "华为全家桶",

        # ----- 智能汽车: 整车品牌 -----
        "问界M5", "问界M7", "问界M8", "问界M9",
        "智界S7", "智界R7",
        "享界S9",
        "尊界S800",
        "尚界",

        # ----- 智能汽车: 智驾方案 -----
        "乾崑ADS 3.0", "乾崑ADS 4.0",
        "途灵底盘", "鸿蒙车机",

        # ----- ToB: AI 算力 / 云 (精简保留) -----
        "昇腾NPU", "Atlas训练集群", "华为云", "ModelArts",

        # ----- ToB: 通信 / 能源 (精简保留) -----
        "5.5G基站", "华为逆变器", "液冷数据中心",
    ],

    # ================================================================
    # chips — 独立维度，覆盖各业务线的核心芯片
    # ================================================================
    "chips": [
        "麒麟9000S", "麒麟9010", "麒麟9020",
        "麒麟9030", "麒麟9030 Pro", "麒麟9030S",
        "麒麟芯片",
        "昇腾910B", "昇腾910C", "昇腾310P",
        "鲲鹏920",
        "巴龙基带",
        "鸿鹄芯片", "凌霄芯片",
    ],

    # ================================================================
    # people
    # ================================================================
    "people": [
        "余承东", "余总", "任正非", "任总",
        "何刚", "靳玉志", "王成录",
    ],

    # ================================================================
    # slogans / 梗
    # ================================================================
    "slogans": [
        # 经典
        "遥遥领先", "用户至上", "中华有为", "国货之光",
        "构建万物互联的智能世界", "没有人能够熄灭满天星光",
        "王者归来", "轻舟已过万重山",
        # 2025-2026
        "赛道传奇", "说一次扣一万", "五界三境",
        "全国笑柄", "含华量", "电子螺丝钉",
    ],

    # ================================================================
    # events
    # ================================================================
    "events": [
        # 制裁
        "美国制裁", "芯片断供", "EUV光刻机禁运", "出售荣耀",
        # 2023-2024
        "Mate 60 无发布会直接开售", "麒麟9000S回归",
        "鸿蒙NEXT发布", "问界M9上市", "享界S9发布",
        # 2025-2026
        "华为2025年营收破8800亿", "鸿蒙中国市场份额超越iOS",
        "Mate 80系列发布", "Pura 90系列发布",
        "Pura 90s海外首发5G", "鸿蒙智行交付破百万",
        "罗永浩遥遥领先全国笑柄事件",
        "华为注册赛道传奇商标", "五界三境品牌体系成型",
        "鸿蒙生态开发者破千万", "尊界S800上市",
    ],

    # ================================================================
    # pain_points
    # ================================================================
    "pain_points": [
        # 手机
        "信号问题", "续航缩水", "品控参差", "系统广告多",
        "价格高/降价背刺", "黄牛加价", "饥饿营销",
        "折叠屏折痕", "多设备协同不稳定",
        # 软件/生态
        "微信适配慢", "应用生态不足",
        "鸿蒙PC迟迟未发布", "系统更新跳票",
        # 售后
        "售后响应慢", "客服排队久",
        # 营销
        "发布会PPT夸大", "赛道传奇名字太土",
        # 汽车
        "含华量被稀释", "智驾订阅费争议", "鸿蒙智行交车慢",
        # ToB
        "昇腾算力价格贵", "华为云续费套路",
    ],

    # ================================================================
    # competitors
    # ================================================================
    "competitors": [
        # 手机
        "苹果", "iPhone", "小米", "OPPO", "vivo", "三星", "荣耀",
        # 汽车
        "特斯拉", "理想", "蔚来", "小鹏", "比亚迪", "小米SU7", "极氪",
        # ToB
        "英伟达", "寒武纪",
    ],
}

# 场景和语气变体
SCENE_VARIANTS = [
    "社交媒体吐槽帖", "数码论坛回帖", "朋友圈动态",
    "微信群聊天", "产品评价区", "视频弹幕",
    "知乎回答", "小红书种草/拔草帖", "微博评论区",
]

TONE_VARIANTS = [
    "口语化，像一个普通用户在吐槽",
    "正式但暗藏讽刺，像数码博主的理性评价",
    "网感强，像B站/小红书年轻用户的表达",
    "中年用户语气，用词克制但态度明显",
    "暴躁老哥风格，直接但有趣",
    "技术宅风格，喜欢用类比和比喻",
]

# ============================================================
# 四、核心生成 Prompt
# ============================================================

SYSTEM_PROMPT = """你是一位精通中文语言学和反讽（讽刺）分析的专家。你的任务是生成高质量的、以华为公司为背景的反讽/非反讽文本样本及对应的思维链分析。

你的输出必须是严谨、准确、多样的。请确保：
1. 文本读起来像真实的中文用户生成的——有口语感、有情绪、有个性
2. 思维链分析严格按照给定的模板结构，每个子字段都要充分展开
3. 情感反转是分析的核心——必须明确标注表面情感和真实情感的方向
4. 伪装机制必须具体——不要笼统说"假装"，要说清楚假装了什么态度/角色
5. 判断依据必须引用文本中的具体词语或句式作为证据
6. 多样化的场景、语气、华为产品/人物/事件——避免重复使用同一实体"""


def build_generation_prompt(category_label: str, count: int,
                            seed_examples: list = None) -> str:
    """为指定分类构建生成提示词"""
    cat = CATEGORY_DEFINITIONS[category_label]
    is_sarc = cat["is_sarcastic"]

    prompt_parts = [f"## 任务：生成 {count} 条「{cat['name']}」样本\n"]

    # 分类定义
    prompt_parts.append(f"### 分类定义")
    prompt_parts.append(f"- 类别：{cat['name']}（{category_label}）")
    prompt_parts.append(f"- 是否反讽：{'是' if is_sarc else '否'}")
    prompt_parts.append(f"- 核心机制：{cat['mechanism']}")
    if is_sarc:
        prompt_parts.append(f"- 伪装类型：{cat['pretense_type']}")
        prompt_parts.append(f"- 情感反转方向：{cat['emotion_direction']}")
    else:
        prompt_parts.append(f"- 易混淆原因：{cat['why_confusable']}")
    prompt_parts.append(f"- 机制说明：{cat['description']}")
    prompt_parts.append(f"\n{cat['generation_guide']}")

    # 华为素材提示
    prompt_parts.append(f"\n### 华为背景素材（可选参考，也可使用其他相关实体）")
    prompt_parts.append(f"- 产品：{', '.join(HUAWEI_ENTITIES['products'][:20])}...")
    prompt_parts.append(f"- 芯片：{', '.join(HUAWEI_ENTITIES['chips'])}")
    prompt_parts.append(f"- 人物：{', '.join(HUAWEI_ENTITIES['people'])}")
    prompt_parts.append(f"- Slogan/梗：{', '.join(HUAWEI_ENTITIES['slogans'])}")
    prompt_parts.append(f"- 事件：{', '.join(HUAWEI_ENTITIES['events'][:10])}...")
    prompt_parts.append(f"- 常见痛点：{', '.join(HUAWEI_ENTITIES['pain_points'][:10])}...")

    # 多样性和语气要求
    prompt_parts.append(f"\n### 多样性要求")
    prompt_parts.append(f"- 场景类型轮换使用：{', '.join(SCENE_VARIANTS)}")
    prompt_parts.append(f"- 语气风格轮换使用：{', '.join(TONE_VARIANTS)}")
    prompt_parts.append(f"- 每条样本使用不同的华为产品/人物/事件作为背景")
    prompt_parts.append(f"- 避免重复使用相同的句式结构")
    prompt_parts.append(f"- 产品、场景、说话者身份在{count}条中要多样化")

    # 种子参考（如有）
    if seed_examples:
        prompt_parts.append(f"\n### 参考种子样本（保持质量标准，但内容必须全新）")
        for i, ex in enumerate(seed_examples[:3], 1):
            prompt_parts.append(f"\n种子{i}：\"{ex['text']}\"")

    # CoT 模板
    prompt_parts.append(f"\n### 每条样本的输出格式（严格遵守）")
    template = COT_TEMPLATE_SARCASTIC if is_sarc else COT_TEMPLATE_NON_SARCASTIC
    prompt_parts.append(f"```\n{template}\n```")

    # CoT 质量要求
    prompt_parts.append(f"\n### 思维链质量要求")
    prompt_parts.append("1. 1.2情感极性：必须明确标注表面用词的情感倾向（正面/负面/中性）")
    prompt_parts.append("2. 1.3背景预设：必须列出至少1-2条读者需要共享的背景知识")
    prompt_parts.append("3. 1.4伪装判断：必须具体说明说话者在'装'什么——装满意？装感激？装无知？装不在意？")
    prompt_parts.append("4. 2.3情感反转：必须说明方向（正→负/负→正/无反转）+ 幅度（强/中/弱）+ 触发点（在哪个词/短语处发生反转）")
    if not is_sarc:
        prompt_parts.append("5. 4.5缺失检查：必须逐一说明缺少了哪个反讽必要条件（语义反转/情感反转/伪装意图），并解释为什么")
    prompt_parts.append("6. 4.1语言线索：必须引用文本中的具体词语/句式作为证据")
    prompt_parts.append("7. 每个子字段至少2-3句话，不能一句话带过")

    # 输出格式
    prompt_parts.append(f"\n### 最终输出格式")
    prompt_parts.append(f"直接输出一个 JSON 数组，每个元素包含以下字段：")
    prompt_parts.append(f'{{"text": "原文", "label": "{category_label}", '
                       f'"category": "{cat["name"]}", '
                       f'"is_sarcastic": {str(is_sarc).lower()}, '
                       f'"cot": "完整的思维链文本（使用\\n换行）"}}')
    prompt_parts.append(f"输出 {count} 条样本。")

    return "\n".join(prompt_parts)


# ============================================================
# 五、质量检查函数
# ============================================================

def check_cot_quality(cot: str, is_sarcastic: bool) -> dict:
    """检查 CoT 是否覆盖了所有必要维度"""
    issues = []
    warnings = []

    # 必要的段标题检查
    required_sections = [
        "【场景/语境】", "【一、表面分析】", "【二、深层分析】",
        "【三、反讽判断】", "【四、判断依据】"
    ]
    for section in required_sections:
        if section not in cot:
            issues.append(f"缺少段落: {section}")

    # 子字段检查
    required_subfields = [
        "1.1 字面含义", "1.2 情感极性", "1.3 背景预设", "1.4 伪装判断",
        "2.1 真实意图", "2.2 真实情感", "2.3 情感反转",
        "3.1 判断结果",
        "4.1 语言线索", "4.2 语境线索", "4.3 情感线索", "4.4 伪装机制",
    ]
    if not is_sarcastic:
        required_subfields.append("4.5 反讽要素缺失检查")

    for subfield in required_subfields:
        if subfield not in cot:
            issues.append(f"缺少子字段: {subfield}")

    # 情感反转方向关键词检查（针对反讽样本）
    if is_sarcastic:
        reversal_keywords = ["正→负", "负→正", "反转", "表面", "实际"]
        if not any(kw in cot for kw in reversal_keywords):
            warnings.append("反讽样本的CoT中未检测到情感反转方向标记（如'正→负'）")

    # 引用原文具体词汇的检查
    # 检查4.1语言线索是否包含引号（表明引用了具体词语）
    if "4.1 语言线索" in cot:
        ling_start = cot.find("4.1 语言线索")
        ling_end = cot.find("4.2 语境线索") if "4.2 语境线索" in cot else len(cot)
        ling_section = cot[ling_start:ling_end]
        # 检查是否引用了具体词语（包含「」或引号标记）
        if "「" not in ling_section and '"' not in ling_section and "——" not in ling_section:
            warnings.append("4.1语言线索可能未引用文本中的具体词语")

    return {"issues": issues, "warnings": warnings, "passed": len(issues) == 0}


def check_diversity(samples: list) -> dict:
    """检查一批样本的多样性"""
    if len(samples) < 2:
        return {"issues": [], "warnings": [], "passed": True}

    texts = [s["text"] for s in samples]

    # 检查是否有完全重复的文本
    if len(set(texts)) < len(texts):
        return {"issues": ["存在完全重复的文本"], "warnings": [], "passed": False}

    # 检查文本长度分布
    lengths = [len(t) for t in texts]
    if max(lengths) - min(lengths) < 10:
        return {"issues": [], "warnings": ["文本长度过于集中，可能缺少长度多样性"], "passed": True}

    # 检查是否有相同句式骨架
    # 简单检查：抽取前5个字符，看是否有重复
    prefixes = [t[:5] for t in texts]
    if len(set(prefixes)) < len(prefixes) * 0.5:
        return {"issues": [], "warnings": [f"开头句式重复率较高 ({len(set(prefixes))}/{len(prefixes)} 种)"], "passed": True}

    return {"issues": [], "warnings": [], "passed": True}


# ============================================================
# 六、生成器类（API调用接口）
# ============================================================

class SarcasmDataGenerator:
    """反讽数据生成器 —— 封装LLM API调用和批处理逻辑"""

    def __init__(self, api_type: str = "openai", model: str = None,
                 api_key: str = None, base_url: str = None):
        """
        api_type: "openai" | "anthropic" | "deepseek"
        model: 模型名称，默认根据api_type自动选择
        """
        self.api_type = api_type
        self.model = model or {
            "openai": "gpt-4o",
            "anthropic": "claude-sonnet-4-20250514",
            "deepseek": "deepseek-chat",
        }.get(api_type, "gpt-4o")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = base_url

    def generate_batch(self, category_label: str, count: int,
                       seed_examples: list = None,
                       batch_size: int = 5) -> list:
        """为一个分类生成一批样本"""
        all_samples = []
        remaining = count

        while remaining > 0:
            current_batch_size = min(batch_size, remaining)
            prompt = build_generation_prompt(category_label, current_batch_size, seed_examples)
            try:
                batch = self._call_llm(prompt, category_label, current_batch_size)
                all_samples.extend(batch)
                remaining -= len(batch)
                print(f"  [{category_label}] 已生成 {len(all_samples)}/{count}", flush=True)
            except Exception as e:
                print(f"  [{category_label}] 批次失败: {e}, 重试中...", flush=True)
                time.sleep(5)

        return all_samples[:count]

    def _call_llm(self, prompt: str, category_label: str, expected_count: int) -> list:
        """调用LLM API"""
        if self.api_type in ("openai", "deepseek"):
            return self._call_openai_compatible(prompt, category_label, expected_count)
        elif self.api_type == "anthropic":
            return self._call_anthropic(prompt, category_label, expected_count)
        else:
            raise ValueError(f"不支持的API类型: {self.api_type}")

    def _call_openai_compatible(self, prompt: str, category_label: str,
                                 expected_count: int) -> list:
        """调用 OpenAI 兼容 API"""
        import requests
        url = self.base_url or "https://api.openai.com/v1/chat/completions"
        if self.api_type == "deepseek" and not self.base_url:
            url = "https://api.deepseek.com/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
            "max_tokens": 16000,
            "response_format": {"type": "json_object"},
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return self._parse_response(content, category_label)

    def _call_anthropic(self, prompt: str, category_label: str,
                         expected_count: int) -> list:
        """调用 Anthropic API"""
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=16000,
            temperature=0.9,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.content[0].text
        return self._parse_response(content, category_label)

    def _parse_response(self, content: str, category_label: str) -> list:
        """解析 LLM 返回的内容为样本列表"""
        # 尝试提取 JSON 数组
        content = content.strip()
        # 移除可能的 markdown 代码块标记
        if content.startswith("```"):
            lines = content.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # 尝试找到JSON数组
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"无法解析LLM返回内容为JSON: {content[:200]}...")

        # 支持 {"samples": [...]} 或直接 [...]
        if isinstance(data, dict):
            samples = data.get("samples", data.get("data", []))
        else:
            samples = data

        # 标准化格式
        for s in samples:
            if "label" not in s:
                s["label"] = category_label
            if "category" not in s:
                s["category"] = CATEGORY_DEFINITIONS[category_label]["name"]
            if "is_sarcastic" not in s:
                s["is_sarcastic"] = CATEGORY_DEFINITIONS[category_label]["is_sarcastic"]

        return samples

    def generate_all(self, samples_per_category: int = 10,
                     categories: list = None,
                     seed_examples: dict = None) -> dict:
        """为所有分类生成样本"""
        if categories is None:
            categories = list(CATEGORY_DEFINITIONS.keys())

        results = {}
        total = 0
        for cat in categories:
            seeds = seed_examples.get(cat, []) if seed_examples else []
            print(f"\n{'='*60}")
            print(f"生成 [{cat}] {CATEGORY_DEFINITIONS[cat]['name']} x{samples_per_category}")
            print(f"{'='*60}")
            samples = self.generate_batch(cat, samples_per_category, seed_examples=seeds)
            results[cat] = samples
            total += len(samples)
            print(f"  [{cat}] 完成: {len(samples)}条")

        print(f"\n总计生成: {total}条")
        return results


# ============================================================
# 七、自助生成（不依赖外部 API 的模板化生成）
# ============================================================

class TemplateBasedGenerator:
    """基于模板的本地生成器——用于快速原型，不需要API密钥"""

    def __init__(self, seed_file: str = None):
        self.seeds = {}
        if seed_file and os.path.exists(seed_file):
            self._load_seeds(seed_file)

    def _load_seeds(self, filepath: str):
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                sample = json.loads(line)
                label = sample["label"]
                if label not in self.seeds:
                    self.seeds[label] = []
                self.seeds[label].append(sample)

    def get_augmentation_templates(self, category_label: str) -> list:
        """获取指定分类的增强模板"""
        cat = CATEGORY_DEFINITIONS[category_label]
        return [
            {
                "name": "换产品",
                "instruction": f"将文本中的华为产品换成另一个华为产品（如从Mate 70换成Pura 80），保持反讽机制不变",
            },
            {
                "name": "换场景",
                "instruction": "将文本中的使用场景换成另一个场景（如从市中心换成地铁/电梯/家里），保持其他不变",
            },
            {
                "name": "换语气",
                "instruction": f"用不同的语气重写文本（如从口语吐槽换成博主评测风），保持反讽机制不变",
            },
            {
                "name": "换句式",
                "instruction": "用不同的句式结构表达同样的反讽（如从直述换成对话体/反问句/段子格式）",
            },
            {
                "name": "调强度",
                "instruction": "调整反讽的显性程度（从微妙暗示→明显阴阳→尖锐攻击，或反之）",
            },
            {
                "name": "加/去标记",
                "instruction": "给文本添加或删除外部标记（emoji、引号、话题标签、狗头等）",
            },
        ]


# ============================================================
# 八、命令行接口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="反讽数据集生成器 —— 基于 PMP + Sarcasm-R1 框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 为S1分类生成10条样本
  python generate_sarcasm_data.py --category S1 --count 10

  # 为所有分类各生成10条
  python generate_sarcasm_data.py --all --samples-per-category 10

  # 使用DeepSeek API生成
  python generate_sarcasm_data.py --all --api deepseek --model deepseek-chat

  # 使用Anthropic API生成
  python generate_sarcasm_data.py --all --api anthropic --model claude-sonnet-4-20250514

  # 加载种子数据作为参考，输出到指定文件
  python generate_sarcasm_data.py --all --seed-file ./seed_100.jsonl --output ./output.jsonl

  # 只生成反讽类（S1-S10）
  python generate_sarcasm_data.py --categories S1,S2,S3,S4,S5,S6,S7,S8,S9,S10 --count 10

  # 只生成非反讽类（N1-N10）
  python generate_sarcasm_data.py --categories N1,N2,N3,N4,N5,N6,N7,N8,N9,N10 --count 10
        """,
    )
    parser.add_argument("--category", type=str, help="单个分类标签（如 S1, N3）")
    parser.add_argument("--categories", type=str, help="多个分类标签，逗号分隔（如 S1,S2,N1）")
    parser.add_argument("--all", action="store_true", help="生成所有20个分类")
    parser.add_argument("--count", type=int, default=10, help="单次生成数量")
    parser.add_argument("--samples-per-category", type=int, default=10, help="每个分类的样本数（与--all配合）")
    parser.add_argument("--api", type=str, default="openai", choices=["openai", "anthropic", "deepseek"])
    parser.add_argument("--model", type=str, help="模型名称")
    parser.add_argument("--api-key", type=str, help="API密钥（也可通过环境变量设置）")
    parser.add_argument("--base-url", type=str, help="API基础URL（用于自定义端点）")
    parser.add_argument("--seed-file", type=str, help="种子数据JSONL文件路径")
    parser.add_argument("--output", type=str, default="./sarcasm_output.jsonl", help="输出文件路径")
    parser.add_argument("--batch-size", type=int, default=5, help="每批生成数量")
    parser.add_argument("--validate", action="store_true", help="生成后运行质量检查")

    args = parser.parse_args()

    # 确定要生成的分类
    if args.category:
        categories = [args.category]
    elif args.categories:
        categories = [c.strip() for c in args.categories.split(",")]
    elif args.all:
        categories = list(CATEGORY_DEFINITIONS.keys())
    else:
        parser.print_help()
        return

    # 验证分类
    for cat in categories:
        if cat not in CATEGORY_DEFINITIONS:
            print(f"错误: 未知分类 '{cat}'。可用分类: {list(CATEGORY_DEFINITIONS.keys())}")
            return

    # 加载种子数据
    seed_examples = None
    if args.seed_file:
        seed_examples = {}
        with open(args.seed_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                sample = json.loads(line)
                label = sample["label"]
                if label not in seed_examples:
                    seed_examples[label] = []
                seed_examples[label].append(sample)
        print(f"已加载种子数据: {sum(len(v) for v in seed_examples.values())}条")

    # 初始化生成器
    generator = SarcasmDataGenerator(
        api_type=args.api,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
    )

    # 批量生成
    count_per = args.samples_per_category if args.all else args.count
    all_samples = []

    for cat in categories:
        seeds = seed_examples.get(cat, []) if seed_examples else []
        samples = generator.generate_batch(
            cat, count_per,
            seed_examples=seeds,
            batch_size=args.batch_size,
        )
        all_samples.extend(samples)

    # 质量验证
    if args.validate:
        print(f"\n{'='*60}")
        print("运行质量检查...")
        print(f"{'='*60}")
        passed = 0
        warned = 0
        failed = 0
        for s in all_samples:
            result = check_cot_quality(s["cot"], s["is_sarcastic"])
            if not result["passed"]:
                failed += 1
                print(f"  [FAIL] {s['label']}: {result['issues']}")
            elif result["warnings"]:
                warned += 1
            else:
                passed += 1
        print(f"  通过: {passed}, 警告: {warned}, 未通过: {failed}")

    # 保存
    with open(args.output, 'w', encoding='utf-8') as f:
        for s in all_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\n已保存 {len(all_samples)} 条样本到: {args.output}")


if __name__ == "__main__":
    main()