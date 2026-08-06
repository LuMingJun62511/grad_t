#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_bridge_data.py — 桥接数据生成脚本

在反讽识别能力与下游任务能力之间架设"桥接数据"，
使模型学会在执行下游任务（情感分析、意图识别等）时，
先感知→确认→翻转反讽语义，再基于真实含义完成任务。

三类桥接 CoT:
  S型（激活路径）: 有反讽 → 确认 → 翻转语义 → 下游任务（基于深层含义）
  N型（快速通过）: 无反讽 → 一句话判断 → 下游任务（基于字面含义）
  C型（排除路径）: 疑似反讽 → 逐条排除 → 下游任务（基于字面含义）

桥接标签格式: BX-{SARC_LABEL}-{TASK_ID}-{BRIDGE_TYPE}
  示例:
    BX-S1-SA-S  : S1直接反话 × 情感分析 × 反讽激活
    BX-N3-IR-C  : N3直接批评 × 意图识别 × 混淆排除

用法:
  # 快速验证：S型 × SA任务 × 2类 × 5条
  python generate_bridge_data.py --bridge-type S --task SA \
      --sarcasm-categories S1,S2 --count 5

  # 全量生成 S型（10反讽类 × 2任务 × 50条 = 1000条）
  python generate_bridge_data.py --bridge-type S --all-tasks \
      --all-sarcasm --samples-per-label 50

  # 全量生成 N型 + C型（10非反讽类 × 2任务 × 30条 × 2类型 = 1200条）
  python generate_bridge_data.py --bridge-type N,C --all-tasks \
      --all-non-sarcasm --samples-per-label 30

  # 一锅端：3类型 × 20类 × 2任务 × 各50/30/30条
  python generate_bridge_data.py --all-bridge-types --all-tasks \
      --all-categories --s-samples 50 --n-samples 30 --c-samples 30

  # 断点续传
  python generate_bridge_data.py ... --resume
"""

import argparse
import json
import os
import re
import sys
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

# ============================================================
# 导入常量
# ============================================================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from _sarcasm_constants import (  # type: ignore
    CATEGORY_DEFINITIONS,
    HUAWEI_ENTITIES,
    SCENE_VARIANTS,
    TONE_VARIANTS,
)

# ============================================================
# 一、下游任务定义
# ============================================================

DOWNSTREAM_TASKS: Dict[str, Dict] = {
    "SA": {
        "id": "SA",
        "name": "情感分析",
        "description": "判断文本表达的真实情感倾向",
        "output_space": ["正面/积极", "负面/消极", "中性"],
        "output_field": "sentiment",
        "output_example": "负面/消极",
        "how_sarcasm_affects": (
            "反讽文本的表面情感与真实情感相反。"
            "例如'正话反说'表面为正面、实际为负面；'反话正说'表面为负面、实际为正面。"
            "必须先识别反讽并翻转语义，才能得到正确的情感标签。"
        ),
        "analysis_guide": (
            "情感分析的关注点：\n"
            "- 关注说话者对评价对象的真实态度（喜欢/厌恶/中立）\n"
            "- 注意情感强度修饰词（'太''极其''有点''略微'）\n"
            "- 如果有反讽，表面情感极性需要反转才是真实情感\n"
            "- 输出格式：正面/积极、负面/消极、中性 三选一"
        ),
    },
    "IR": {
        "id": "IR",
        "name": "意图识别",
        "description": "判断说话者发这段话的真实意图/目的",
        "output_space": ["投诉/抱怨", "询问/求助", "建议/推荐", "分享/讨论", "炫耀/展示", "吐槽/调侃"],
        "output_field": "intent",
        "output_example": "投诉/抱怨",
        "how_sarcasm_affects": (
            "反讽文本的措辞方式可能伪装了真实意图。"
            "例如表面在'夸奖'实际的投诉，表面在'询问'实际的嘲讽，"
            "表面在'分享'实际的炫耀。必须先识别反讽并还原真实表达方式，"
            "才能判断真实的交际意图。"
        ),
        "analysis_guide": (
            "意图识别的关注点：\n"
            "- 关注说话者的交际目的（想达到什么效果）\n"
            "- 反讽可能把投诉包装成赞美、把嘲讽包装成询问\n"
            "- 判断时看真实意图而非措辞形式\n"
            "- 输出从六类中选一：投诉/抱怨、询问/求助、建议/推荐、分享/讨论、炫耀/展示、吐槽/调侃"
        ),
    },
}

# ============================================================
# 二、桥接 CoT 模板
# ============================================================

# ---- S型：反讽激活路径 ----
COT_TEMPLATE_BRIDGE_S = """【一、反讽感知】
1.1 信号扫描：
{signal_scan}

1.2 感知结论：
{perception_conclusion}

【二、反讽确认】
2.1 表面-真实对照：
- 字面表达：{literal_expression}
- 真实意图：{true_intent}
- 反讽机制：{sarcasm_mechanism}

2.2 情感反转确认：
{emotion_reversal_confirm}

2.3 确认结论：是反讽 ✓

【三、语义还原】
3.1 翻转方式：
{inversion_strategy}

3.2 还原后的等价直白表达：
{restored_literal_text}

【四、{task_name}分析】（基于真实语义）
4.1 分析过程：
{task_reasoning}

4.2 {task_output_field}：{task_result}"""

# ---- N型：快速通过路径 ----
COT_TEMPLATE_BRIDGE_N = """【一、反讽感知】
1.1 信号扫描：
{signal_scan}

1.2 感知结论：文本无明显反讽信号（无情感反转、无伪装意图、修辞特征与情感方向一致），按字面含义理解。

【二、{task_name}分析】（基于字面语义）
2.1 分析过程：
{task_reasoning}

2.2 {task_output_field}：{task_result}"""

# ---- C型：混淆排除路径 ----
COT_TEMPLATE_BRIDGE_C = """【一、反讽感知】
1.1 信号扫描：
{signal_scan}

1.2 感知结论：文本存在疑似反讽特征，需进一步判断。

【二、反讽排除】
2.1 疑似反讽点：
{suspected_sarcasm_points}

2.2 排除分析：
{exclusion_reasoning}

2.3 关键区分依据：
{key_differentiator}

2.4 最终判定：不是反讽 ✗

【三、{task_name}分析】（基于字面语义）
3.1 分析过程：
{task_reasoning}

3.2 {task_output_field}：{task_result}"""


# ============================================================
# 三、桥接标签体系
# ============================================================

def build_bridge_labels(
    sarcasm_labels: List[str],
    task_ids: List[str],
    bridge_type: str,
) -> List[Dict]:
    """构建桥接数据标签列表。

    Args:
        sarcasm_labels: 反讽/非反讽分类标签 (S1-S10 或 N1-N10)
        task_ids: 下游任务ID (SA, IR, ...)
        bridge_type: 桥接类型 (S, N, C)

    Returns:
        [{"bridge_label": "BX-S1-SA-S", "sarcasm_label": "S1",
          "task_id": "SA", "bridge_type": "S"}, ...]
    """
    labels = []
    for sl in sarcasm_labels:
        for tid in task_ids:
            bridge_label = f"BX-{sl}-{tid}-{bridge_type}"
            labels.append({
                "bridge_label": bridge_label,
                "sarcasm_label": sl,
                "task_id": tid,
                "bridge_type": bridge_type,
            })
    return labels


def describe_bridge_type(bridge_type: str) -> str:
    """返回桥接类型的中文描述。"""
    return {
        "S": "S型（反讽激活路径）：文本确实有反讽 → 确认 → 翻转语义 → 基于深层/真实含义执行下游任务",
        "N": "N型（快速通过路径）：文本无明显反讽信号 → 一句话判断通过 → 基于字面含义执行下游任务",
        "C": "C型（混淆排除路径）：文本有疑似反讽特征但实际不是反讽 → 逐条分析排除 → 基于字面含义执行下游任务",
    }.get(bridge_type, bridge_type)


def get_bridge_cot_template(bridge_type: str, task_id: str) -> str:
    """获取指定桥接类型和下游任务的 CoT 模板。"""
    task_def = DOWNSTREAM_TASKS[task_id]

    if bridge_type == "S":
        template = COT_TEMPLATE_BRIDGE_S
    elif bridge_type == "N":
        template = COT_TEMPLATE_BRIDGE_N
    else:  # C
        template = COT_TEMPLATE_BRIDGE_C

    return template.format(
        task_name=task_def["name"],
        task_output_field=task_def["output_field"],
        task_result=f"{{{{任务输出：{task_def['output_example']}等}}}}",
        signal_scan="{{简述文本中观察到什么特征}}",
        perception_conclusion="{{初步判断有无反讽信号及原因}}",
        literal_expression="{{字面上在说什么}}",
        true_intent="{{实际上想表达什么}}",
        sarcasm_mechanism="{{使用了什么反讽机制}}",
        emotion_reversal_confirm="{{情感方向的反转：正→负 / 负→正 + 强度 + 触发点}}",
        inversion_strategy="{{如何把反讽表达翻转为直白表达}}",
        restored_literal_text="{{去掉反讽包装后的等价直白句子}}",
        task_reasoning="{{基于真实语义的任务分析过程}}",
        suspected_sarcasm_points="{{哪些表达看起来像反讽}}",
        exclusion_reasoning="{{为什么这些不是真正的反讽}}",
        key_differentiator="{{区分此类文本与真正反讽的关键依据}}",
    )


# ============================================================
# 四、桥接 Prompt 构建器
# ============================================================

BRIDGE_SYSTEM_PROMPT = """你是一位精通中文语言学和NLP标注的专家。
你的任务是生成"桥接数据"——将反讽识别能力与下游任务分析能力连接起来的训练样本。

核心要求：
1. 文本读起来像真实的中文用户生成的——有口语感、有情绪、有个性
2. 文本背景以华为公司及其产品/服务为中心
3. 思维链（CoT）必须严格按照给定的模板结构，每个字段充分展开
4. 反讽判断与下游任务输出之间必须有清晰的因果连接
5. 下游任务的分析必须基于正确的语义层（反讽文本基于深层含义，非反讽文本基于字面含义）
6. 多样化的场景、语气、产品——避免重复使用同一实体"""


class BridgePromptBuilder:
    """桥接数据 Prompt 构建器。"""

    @staticmethod
    def build_generation_prompt(
        bridge_label_info: Dict,
        count: int,
        seed_examples: Optional[List[Dict]] = None,
        diversity_specs: Optional[List[Dict]] = None,
    ) -> str:
        """为指定的桥接标签构建一批样本的生成 prompt。

        Args:
            bridge_label_info: 包含 bridge_label, sarcasm_label, task_id, bridge_type
            count: 本批生成条数
            seed_examples: 种子样本
            diversity_specs: 多样性约束列表
        """
        sarcasm_label = bridge_label_info["sarcasm_label"]
        task_id = bridge_label_info["task_id"]
        bridge_type = bridge_label_info["bridge_type"]
        bridge_label = bridge_label_info["bridge_label"]

        cat_def = CATEGORY_DEFINITIONS[sarcasm_label]
        task_def = DOWNSTREAM_TASKS[task_id]
        is_sarcastic = cat_def.get("is_sarcastic", False)

        parts = []

        # ---- 总体任务 ----
        parts.append(f"## 桥接数据生成任务：{bridge_label}")
        parts.append(f"本批生成 {count} 条样本。")
        parts.append("")

        # ---- 桥接类型说明 ----
        parts.append(f"### 桥接类型：{describe_bridge_type(bridge_type)}")
        parts.append("")

        # ---- 文本风格约束 ----
        parts.append(f"### 文本风格约束（基于反讽分类「{cat_def['name']}」）")
        parts.append(f"- 是否反讽：{'是' if is_sarcastic else '否'}")
        if is_sarcastic:
            parts.append(f"- 反讽机制：{cat_def['mechanism']}")
            parts.append(f"- 伪装类型：{cat_def['pretense_type']}")
            parts.append(f"- 情感方向：{cat_def['emotion_direction']}")
        else:
            parts.append(f"- 易混淆原因：{cat_def['why_confusable']}")
        parts.append(f"- 分类说明：{cat_def['description']}")
        parts.append(f"\n{cat_def['generation_guide']}")
        parts.append("")

        # ---- 下游任务 ----
        parts.append(f"### 下游任务：{task_def['name']}（{task_id}）")
        parts.append(f"- 任务说明：{task_def['description']}")
        parts.append(f"- 输出空间：{' / '.join(task_def['output_space'])}")
        parts.append(f"- 反讽对任务的影响：{task_def['how_sarcasm_affects']}")
        parts.append(f"- 分析指南：")
        parts.append(f"  {task_def['analysis_guide']}")
        parts.append("")

        # ---- 桥接逻辑说明 ----
        parts.append(f"### 桥接逻辑（必须严格遵守）")
        if bridge_type == "S":
            parts.append("这是一条**反讽激活**路径：")
            parts.append("1. 文本使用了上述反讽机制（是真正的反讽文本）")
            parts.append(f"2. CoT中先感知→确认反讽，然后翻转语义")
            parts.append(f"3. {task_def['name']}的分析基于**翻转后的真实语义**")
            parts.append(f"4. 任务的输出结果应当与深层含义一致（不能与表面含义一致）")
            parts.append(f"5. 示例：正话反说的文本表面赞美、实际批评 → 情感分析输出应为'负面/消极'")
        elif bridge_type == "N":
            parts.append("这是一条**快速通过**路径：")
            parts.append("1. 文本与上述非反讽分类一致——**明显不是反讽**，没有需要翻转的语义")
            parts.append("2. CoT中反讽感知环节很简短——一句话判断无信号、跳过")
            parts.append("3. 不做深度反讽分析，直接进入下游任务")
            parts.append("4. 下游任务分析基于字面含义")
            parts.append("5. 文本应简单明了，即使粗略一扫也能判断不是反讽")
        else:  # C
            parts.append("这是一条**混淆排除**路径：")
            parts.append("1. 文本与上述非反讽分类一致——有该分类的典型易混淆特征")
            parts.append("2. 文本**看起来像反讽**（有夸张/对比/表面矛盾等），但**实际上不是**")
            parts.append("3. CoT中先扫描出可疑点，然后逐条分析为什么不是反讽")
            parts.append("4. 排除反讽后，下游任务分析基于字面含义")
            parts.append("5. 关键：要清楚解释为什么这个文本与真正的反讽不同（引用该分类的区分标准）")
        parts.append("")

        # ---- 华为素材 ----
        parts.append(f"### 华为背景素材（可选参考，也可使用同行业其他实体）")
        parts.append(f"- 产品：{', '.join(HUAWEI_ENTITIES['products'][:15])}...")
        parts.append(f"- 痛点：{', '.join(HUAWEI_ENTITIES['pain_points'][:10])}...")
        parts.append(f"- 事件：{', '.join(HUAWEI_ENTITIES['events'][:8])}...")
        parts.append("")

        # ---- 多样性约束 ----
        if diversity_specs:
            parts.append(BridgePromptBuilder._build_diversity_section(diversity_specs))
            parts.append("")

        # ---- 种子参考 ----
        if seed_examples:
            parts.append(f"### 参考种子样本（保持质量标准，但内容必须全新）")
            for i, ex in enumerate(seed_examples[:3], 1):
                parts.append(f"\n种子{i}：\"{ex.get('text', ex)}\"")
            parts.append("")

        # ---- CoT模板 ----
        parts.append(f"### 每条样本的 CoT 结构（严格遵守，占位符需填写完整）")
        cot_template = get_bridge_cot_template(bridge_type, task_id)
        parts.append(f"```")
        parts.append(cot_template)
        parts.append(f"```")
        parts.append("")

        # ---- 质量要求 ----
        parts.append(f"### CoT 质量要求")
        if bridge_type == "S":
            parts.append("1. 1.1信号扫描：必须引用文本中的具体词语作为反讽信号")
            parts.append("2. 2.1表面-真实对照：必须明确字面表达了什么、实际上想表达什么（两者方向相反）")
            parts.append("3. 2.2情感反转确认：必须标注反转方向（正→负/负→正）、反转强度、触发点")
            parts.append("4. 3.1翻转方式：必须具体说明翻转策略（取反/降维/还原比例等）")
            parts.append("5. 3.2还原直白表达：必须写出翻转后的等价句子（证明翻转是可行的）")
            parts.append(f"6. 4.1分析过程：必须基于还原后的含义进行分析")
        elif bridge_type == "N":
            parts.append("1. 1.1信号扫描：简明扼要，一句话交代看到的特征即可（不超过3句话）")
            parts.append("2. 1.2感知结论：明确说'无明显反讽信号，按字面理解'")
            parts.append("3. 不做深度反讽分析——不需要分析伪装机制、情感反转等")
            parts.append(f"4. 2.1分析过程：直接基于字面含义进行{task_def['name']}分析")
        else:  # C
            parts.append("1. 1.1信号扫描：引用文本中具体哪些地方看起来像反讽")
            parts.append("2. 2.1疑似反讽点：逐条列出疑点，每条对应一个具体文本片段")
            parts.append("3. 2.2排除分析：对每个疑点解释为什么不是反讽（引用分类区分标准）")
            parts.append("4. 2.3关键区分依据：给出一个可操作的区分规则")
            parts.append(f"5. 3.1分析过程：排除反讽后，基于字面含义分析")

        parts.append("6. 每个子字段至少填充2-3句话，占位符不要留空")
        parts.append("7. 文本长度建议30-150字，自然口语化表达")
        parts.append("")

        # ---- 输出格式 ----
        parts.append(f"### 最终输出格式")
        parts.append(f"直接输出一个 JSON 数组，每个元素包含以下字段：")
        parts.append(json.dumps({
            "text": "原文（带反讽/非反讽的华为场景用户文本）",
            "bridge_label": bridge_label,
            "sarcasm_label": sarcasm_label,
            "task_id": task_id,
            "bridge_type": bridge_type,
            "is_sarcastic": is_sarcastic,
            "cot": "完整的 CoT 文本（使用\\n换行，按照上述模板填写所有占位符）",
            "task_output": f"{task_def['output_example']}",
        }, ensure_ascii=False, indent=2))
        parts.append(f"输出 {count} 条样本。")

        return "\n".join(parts)

    @staticmethod
    def _build_diversity_section(specs: List[Dict]) -> str:
        """构建多样性约束文本。"""
        lines = [
            "### 🎯 本批次每条样本的硬性约束（必须严格遵守，否则视为不合格）",
        ]
        for i, spec in enumerate(specs, 1):
            parts_line = [
                f"- 第{i}条：",
                f"{spec.get('length_label', '中')}文本({spec.get('min_len', 30)}-{spec.get('max_len', 150)}字)",
                f"| 场景={spec.get('scene', '社交媒体')}",
                f"| 语气={spec.get('tone', '口语化')}",
                f"| 关注={spec.get('category', '手机产品')}",
            ]
            if spec.get("intensity"):
                parts_line.append(f"| 反讽显性程度={spec['intensity']}")
            lines.append(" ".join(parts_line))
        lines.append("")
        lines.append("注意：文本字数必须落在指定范围内，不是建议，是硬性要求。")
        return "\n".join(lines)


# ============================================================
# 五、多样性控制器（桥接版）
# ============================================================

# 产品品类
PRODUCT_CATEGORIES = [
    "手机旗舰 (Mate/Pura系列)",
    "折叠屏手机",
    "中端/性价比手机 (nova/畅享)",
    "PC/平板 (MateBook/MatePad)",
    "穿戴/音频 (Watch/FreeBuds)",
    "智能汽车 (问界/智界/享界/尊界)",
    "芯片/底层技术 (麒麟/昇腾/鲲鹏/鸿蒙)",
    "ToB/企业业务 (华为云/昇腾NPU/5.5G)",
]

# 反讽显性程度（仅 S 型使用）
INTENSITY_LEVELS = [
    "微妙暗示——不仔细读看不出来在讽刺",
    "明显阴阳——读者一眼能看出在说反话",
    "尖锐攻击——讽刺力度很强，几乎等于开骂",
]


class BridgeDiversityController:
    """桥接数据的多样性控制器。

    轮换维度：场景、语气、长度、产品品类、（反讽显性程度，仅S型）
    """

    LENGTH_BUCKETS = [
        ("短", 25, 55),
        ("中", 50, 100),
        ("长", 90, 160),
    ]

    def __init__(self, seed: int = 42):
        import random
        self._rng = random.Random(seed)
        self._scenes = list(SCENE_VARIANTS)
        self._tones = list(TONE_VARIANTS)
        self._categories = list(PRODUCT_CATEGORIES)
        self._intensities = list(INTENSITY_LEVELS)
        self._rng.shuffle(self._scenes)
        self._rng.shuffle(self._tones)
        self._rng.shuffle(self._categories)
        self._rng.shuffle(self._intensities)

        self._scene_ptr = 0
        self._tone_ptr = 0
        self._len_ptr = 0
        self._cat_ptr = 0
        self._intensity_ptr = 0
        self._used_combos: set = set()

    def next_batch_specs(self, batch_size: int, bridge_type: str) -> List[Dict]:
        """为下一批桥接数据生成多样性约束。"""
        specs = []
        for _ in range(batch_size):
            spec = {
                "scene": self._scenes[self._scene_ptr % len(self._scenes)],
                "tone": self._tones[self._tone_ptr % len(self._tones)],
                "length_label": self.LENGTH_BUCKETS[self._len_ptr % 3][0],
                "min_len": self.LENGTH_BUCKETS[self._len_ptr % 3][1],
                "max_len": self.LENGTH_BUCKETS[self._len_ptr % 3][2],
                "category": self._categories[self._cat_ptr % len(self._categories)],
                "intensity": (self._intensities[self._intensity_ptr % 3]
                             if bridge_type == "S" else None),
            }

            combo_key = (spec["scene"], spec["tone"], spec["length_label"],
                        spec["category"], spec.get("intensity", ""))
            skip_count = 0
            while combo_key in self._used_combos and skip_count < 50:
                self._len_ptr += 1
                spec["length_label"] = self.LENGTH_BUCKETS[self._len_ptr % 3][0]
                spec["min_len"] = self.LENGTH_BUCKETS[self._len_ptr % 3][1]
                spec["max_len"] = self.LENGTH_BUCKETS[self._len_ptr % 3][2]
                combo_key = (spec["scene"], spec["tone"], spec["length_label"],
                            spec["category"], spec.get("intensity", ""))
                skip_count += 1

            self._used_combos.add(combo_key)
            specs.append(spec)

            self._scene_ptr += 1
            self._tone_ptr += 1
            self._len_ptr += 1
            self._cat_ptr += 1
            self._intensity_ptr += 1

        return specs


# ============================================================
# 六、增量 JSONL 写入器
# ============================================================

class IncrementalWriter:
    """增量 JSONL 写入器（与 v2 一致）。"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.count = 0
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                self.count = sum(1 for line in f if line.strip())
        self._fd = None

    def __enter__(self):
        self._fd = open(self.filepath, "a", encoding="utf-8")
        return self

    def __exit__(self, *args):
        if self._fd:
            self._fd.close()
            self._fd = None

    def write_batch(self, samples: List[Dict]) -> None:
        for s in samples:
            self._fd.write(json.dumps(s, ensure_ascii=False) + "\n")
        self._fd.flush()
        os.fsync(self._fd.fileno())
        self.count += len(samples)
        print(f"  [落库] +{len(samples)}条 → {self.filepath}  (累计 {self.count} 条)",
              flush=True)

    def write_one(self, sample: Dict) -> None:
        self.write_batch([sample])

    def get_existing_bridge_labels(self) -> Dict[str, int]:
        """读取已有输出文件，返回每个 bridge_label 的已有条数。"""
        counts: Dict[str, int] = {}
        if not os.path.exists(self.filepath):
            return counts
        with open(self.filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                    lbl = s.get("bridge_label", s.get("label", "__unknown__"))
                    counts[lbl] = counts.get(lbl, 0) + 1
                except json.JSONDecodeError:
                    pass
        return counts


# ============================================================
# 七、桥接数据生成器
# ============================================================

# DeepSeek Anthropic 端点
DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com/anthropic"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-pro"


class BridgeDataGenerator:
    """桥接数据生成器 —— 走 Anthropic Messages API 格式。"""

    def __init__(
        self,
        base_url: str = DEEPSEEK_DEFAULT_BASE,
        model: str = DEEPSEEK_DEFAULT_MODEL,
        api_key: str = "",
        temperature: float = 0.9,
        max_tokens: int = 16000,
        timeout: int = 180,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._diversity = BridgeDiversityController()
        self._prompt_builder = BridgePromptBuilder()

    # ---- 底层 API 调用 ----

    def _call_api(self, prompt: str, bridge_label: str,
                  expected_count: int) -> List[Dict]:
        """调用 Anthropic Messages API。"""
        url = f"{self.base_url}/v1/messages"

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": BRIDGE_SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        resp = requests.post(url, headers=headers, json=payload,
                            timeout=self.timeout)

        if resp.status_code == 401:
            headers2 = {
                "Authorization": f"Bearer {self.api_key}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            resp = requests.post(url, headers=headers2, json=payload,
                                timeout=self.timeout)

        resp.raise_for_status()
        data = resp.json()

        content_blocks = data.get("content", [])
        text_parts = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block["text"])
        raw_text = "\n".join(text_parts)

        if not raw_text.strip():
            raise ValueError(f"API 返回空文本。usage={data.get('usage')}")

        return self._parse_response(raw_text, bridge_label)

    # ---- 响应解析 ----

    @staticmethod
    def _parse_response(content: str, bridge_label: str) -> List[Dict]:
        """从 LLM 返回中提取 JSON 数组（多层回退）。"""
        content = content.strip()

        # 1) 直接解析
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = None

        # 2) 去 markdown 代码块
        if data is None:
            cleaned = content
            for fence in ["```json", "```"]:
                if cleaned.startswith(fence):
                    cleaned = cleaned[len(fence):].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                data = None

        # 3) 正则找 JSON 数组
        if data is None:
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    data = None

        # 4) 正则找 JSON 对象
        if data is None:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        if data is None:
            snippet = content[:500].replace("\n", "\\n")
            raise ValueError(f"无法从 LLM 响应中解析 JSON。前 500 字符: {snippet}")

        # 标准化为列表
        if isinstance(data, dict):
            samples = data.get("samples", data.get("data", []))
        elif isinstance(data, list):
            samples = data
        else:
            raise ValueError(f"意外的响应类型: {type(data)}")

        # 补全缺失字段
        for s in samples:
            if "bridge_label" not in s:
                s["bridge_label"] = bridge_label

        return samples

    # ---- 批量生成 ----

    def generate_batch(
        self,
        bridge_label_info: Dict,
        count: int,
        seed_examples: Optional[List[Dict]] = None,
        batch_size: int = 5,
        on_batch: Optional[Callable[[List[Dict]], None]] = None,
        max_retries: int = 3,
    ) -> List[Dict]:
        """为一个桥接标签生成指定数量的样本。"""
        all_samples: List[Dict] = []
        remaining = count

        while remaining > 0:
            current_batch_size = min(batch_size, remaining)

            # 获取多样性约束
            div_specs = self._diversity.next_batch_specs(
                current_batch_size, bridge_label_info["bridge_type"])

            # 构建 prompt
            prompt = self._prompt_builder.build_generation_prompt(
                bridge_label_info, current_batch_size,
                seed_examples=seed_examples,
                diversity_specs=div_specs,
            )

            batch = None
            for attempt in range(1, max_retries + 1):
                try:
                    batch = self._call_api(
                        prompt, bridge_label_info["bridge_label"],
                        current_batch_size)
                    break
                except Exception as e:
                    print(f"  [{bridge_label_info['bridge_label']}] "
                          f"第{attempt}次尝试失败: {e}", flush=True)
                    if attempt < max_retries:
                        wait = 2 ** attempt
                        print(f"  [{bridge_label_info['bridge_label']}] "
                              f"等待{wait}秒后重试...", flush=True)
                        time.sleep(wait)
                    else:
                        print(f"  [{bridge_label_info['bridge_label']}] "
                              f"已达最大重试次数，跳过本批",
                              file=sys.stderr, flush=True)
                        batch = []

            if batch:
                all_samples.extend(batch)
                remaining -= len(batch)
                if on_batch:
                    on_batch(batch)
                print(f"  [{bridge_label_info['bridge_label']}] "
                      f"进度 {len(all_samples)}/{count}", flush=True)
            else:
                print(f"  [{bridge_label_info['bridge_label']}] "
                      f"本批为空，终止生成", file=sys.stderr)
                break

        return all_samples[:count]


# ============================================================
# 八、质量检查
# ============================================================

def check_bridge_cot_quality(sample: Dict) -> Dict:
    """检查桥接 CoT 的质量。"""
    cot = sample.get("cot", "")
    bridge_type = sample.get("bridge_type", "")
    task_id = sample.get("task_id", "")

    issues = []
    warnings = []

    if bridge_type == "S":
        required_sections = [
            "【一、反讽感知】", "【二、反讽确认】",
            "【三、语义还原】",
        ]
        required_subfields = [
            "1.1 信号扫描", "1.2 感知结论",
            "2.1 表面-真实对照", "2.2 情感反转确认", "2.3 确认结论",
            "3.1 翻转方式", "3.2 还原后的等价直白表达",
        ]
        # S型必须有"是反讽"的确认
        if "是反讽" not in cot:
            issues.append("S型CoT中未找到'是反讽 ✓'确认")
    elif bridge_type == "N":
        required_sections = ["【一、反讽感知】"]
        required_subfields = ["1.1 信号扫描", "1.2 感知结论"]
        # N型不能有深度反讽分析
        if "【二、反讽确认】" in cot or "【二、反讽排除】" in cot:
            warnings.append("N型CoT不应包含深度反讽分析段落")
    else:  # C
        required_sections = [
            "【一、反讽感知】", "【二、反讽排除】",
        ]
        required_subfields = [
            "1.1 信号扫描", "1.2 感知结论",
            "2.1 疑似反讽点", "2.2 排除分析",
            "2.3 关键区分依据", "2.4 最终判定",
        ]
        if "不是反讽" not in cot:
            issues.append("C型CoT中未找到'不是反讽 ✗'判定")

    for section in required_sections:
        if section not in cot:
            issues.append(f"缺少段落: {section}")
    for subfield in required_subfields:
        if subfield not in cot:
            issues.append(f"缺少子字段: {subfield}")

    # 检查下游任务段落
    task_def = DOWNSTREAM_TASKS.get(task_id, {})
    task_name = task_def.get("name", "")
    task_field = task_def.get("output_field", "")
    if task_name and f"【四、{task_name}分析】" not in cot and f"【二、{task_name}分析】" not in cot and f"【三、{task_name}分析】" not in cot:
        issues.append(f"CoT中未找到下游任务'{task_name}'的分析段落")
    if task_field and task_field not in cot:
        issues.append(f"CoT中未找到任务输出字段'{task_field}'")

    # 检查 task_output 字段
    task_output = sample.get("task_output", "")
    if not task_output:
        issues.append("缺少'task_output'字段")

    return {"issues": issues, "warnings": warnings, "passed": len(issues) == 0}


# ============================================================
# 九、命令行接口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="桥接数据生成器 —— 连接反讽识别与下游任务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 快速验证：S型 × SA任务 × 2类 × 5条
  python generate_bridge_data.py --bridge-type S --task SA \\
      --categories S1,S2 --count 5

  # 全量 S型（10反讽类 × 2任务 × 50条 = 1000条）
  python generate_bridge_data.py --bridge-type S --all-tasks \\
      --all-sarcasm --samples-per-label 50

  # 全量 N型 + C型（10非反讽类 × 2任务 × 30条 × 2类型 = 1200条）
  python generate_bridge_data.py --bridge-type N,C --all-tasks \\
      --all-non-sarcasm --samples-per-label 30

  # 一锅端全量：S型50条/类 + N型30条/类 + C型30条/类
  python generate_bridge_data.py --all-bridge-types --all-tasks \\
      --all-categories --s-samples 50 --n-samples 30 --c-samples 30

  # 断点续传
  python generate_bridge_data.py --all-bridge-types --all-tasks \\
      --all-categories --s-samples 50 --n-samples 30 --c-samples 30 --resume
""",
    )

    # ---- 桥接类型 ----
    g_bt = parser.add_mutually_exclusive_group(required=True)
    g_bt.add_argument("--bridge-type", type=str,
                      help="桥接类型: S/N/C，多个用逗号分隔（如 S,N,C）")
    g_bt.add_argument("--all-bridge-types", action="store_true",
                      help="生成全部三种桥接类型（S/N/C）")

    # ---- 下游任务 ----
    g_task = parser.add_mutually_exclusive_group(required=True)
    g_task.add_argument("--task", type=str,
                       help="下游任务ID，多个用逗号分隔（如 SA,IR）")
    g_task.add_argument("--all-tasks", action="store_true",
                        help="生成全部下游任务（SA/IR）")

    # ---- 分类选择 ----
    g_cat = parser.add_mutually_exclusive_group(required=True)
    g_cat.add_argument("--categories", type=str,
                       help="反讽分类标签，逗号分隔（如 S1,S2,N1,N2）")
    g_cat.add_argument("--all-sarcasm", action="store_true",
                       help="全部反讽类（S1-S10）")
    g_cat.add_argument("--all-non-sarcasm", action="store_true",
                       help="全部非反讽类（N1-N10）")
    g_cat.add_argument("--all-categories", action="store_true",
                       help="全部20个分类（S1-S10 + N1-N10）")

    # ---- 数量 ----
    parser.add_argument("--count", type=int, default=10,
                        help="每个桥接标签的生成数量（单类型模式下）")
    parser.add_argument("--samples-per-label", type=int, default=10,
                        help="每个桥接标签的生成数量（多类型模式下）")
    parser.add_argument("--s-samples", type=int, default=50,
                        help="S型每个桥接标签的生成数量")
    parser.add_argument("--n-samples", type=int, default=30,
                        help="N型每个桥接标签的生成数量")
    parser.add_argument("--c-samples", type=int, default=30,
                        help="C型每个桥接标签的生成数量")

    # ---- API 配置 ----
    parser.add_argument("--base-url", type=str,
                        default=os.environ.get("ANTHROPIC_BASE_URL",
                                               DEEPSEEK_DEFAULT_BASE),
                        help=f"API 基础 URL (default: {DEEPSEEK_DEFAULT_BASE})")
    parser.add_argument("--model", type=str,
                        default=DEEPSEEK_DEFAULT_MODEL,
                        help=f"模型名称 (default: {DEEPSEEK_DEFAULT_MODEL})")
    parser.add_argument("--api-key", type=str,
                        default=os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
                        help="API Key (default: 读取 ANTHROPIC_AUTH_TOKEN 环境变量)")

    # ---- 生成参数 ----
    parser.add_argument("--batch-size", type=int, default=5,
                        help="每批 LLM 调用生成条数 (default: 5)")
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--timeout", type=int, default=180)

    # ---- 输出 ----
    parser.add_argument("--output", type=str, default="./bridge_data_output.jsonl",
                        help="输出 JSONL 文件路径 (default: ./bridge_data_output.jsonl)")
    parser.add_argument("--flush-every", type=int, default=0,
                        help="累积多少条后强制落库 (default: 0=每批都落)")

    # ---- 其他 ----
    parser.add_argument("--seed-file", type=str,
                        help="种子数据 JSONL 文件路径（用于few-shot参考）")
    parser.add_argument("--validate", action="store_true",
                        help="生成后运行质量检查")
    parser.add_argument("--resume", action="store_true",
                        help="断点续传：读取已有输出文件，只补未完成的桥接标签")

    args = parser.parse_args()

    # ---- 解析桥接类型 ----
    if args.all_bridge_types:
        bridge_types = ["S", "N", "C"]
    else:
        bridge_types = [bt.strip() for bt in args.bridge_type.split(",")]
        for bt in bridge_types:
            if bt not in ("S", "N", "C"):
                print(f"错误: 未知桥接类型 '{bt}'。可选: S, N, C")
                sys.exit(1)

    # ---- 解析下游任务 ----
    if args.all_tasks:
        task_ids = list(DOWNSTREAM_TASKS.keys())
    else:
        task_ids = [t.strip() for t in args.task.split(",")]
        for t in task_ids:
            if t not in DOWNSTREAM_TASKS:
                print(f"错误: 未知下游任务 '{t}'。可选: {list(DOWNSTREAM_TASKS.keys())}")
                sys.exit(1)

    # ---- 解析分类 ----
    if args.all_categories:
        categories = list(CATEGORY_DEFINITIONS.keys())
    elif args.all_sarcasm:
        categories = [k for k, v in CATEGORY_DEFINITIONS.items() if v.get("is_sarcastic")]
    elif args.all_non_sarcasm:
        categories = [k for k, v in CATEGORY_DEFINITIONS.items() if not v.get("is_sarcastic")]
    else:
        categories = [c.strip() for c in args.categories.split(",")]
        for c in categories:
            if c not in CATEGORY_DEFINITIONS:
                print(f"错误: 未知分类 '{c}'。可用: {list(CATEGORY_DEFINITIONS.keys())}")
                sys.exit(1)

    # ---- 验证分类与桥接类型的兼容性 ----
    sarcastic_cats = [c for c in categories if CATEGORY_DEFINITIONS[c].get("is_sarcastic")]
    non_sarcastic_cats = [c for c in categories if not CATEGORY_DEFINITIONS[c].get("is_sarcastic")]

    warnings_shown = set()
    for bt in bridge_types:
        if bt == "S":
            if not sarcastic_cats and "S" not in warnings_shown:
                print("⚠ S型桥接需要反讽类（S1-S10），但未选择反讽类 → 自动跳过S型")
                warnings_shown.add("S")
        elif bt in ("N", "C"):
            if not non_sarcastic_cats and bt not in warnings_shown:
                print(f"⚠ {bt}型桥接需要非反讽类（N1-N10），但未选择非反讽类 → 自动跳过{bt}型")
                warnings_shown.add(bt)

    # ---- 构建桥接标签列表 ----
    bridge_labels: List[Dict] = []
    for bt in bridge_types:
        if bt == "S":
            cats = sarcastic_cats
        else:
            cats = non_sarcastic_cats
        if not cats:
            continue
        bridge_labels.extend(build_bridge_labels(cats, task_ids, bt))

    if not bridge_labels:
        print("错误：没有可生成的桥接标签。请检查分类与桥接类型的兼容性。")
        sys.exit(1)

    # ---- 每标签数量 ----
    def get_count_per_label(bt: str) -> int:
        if args.all_bridge_types:
            return {"S": args.s_samples, "N": args.n_samples, "C": args.c_samples}[bt]
        return args.samples_per_label if (len(bridge_types) > 1 or len(task_ids) > 1 or len(categories) > 1) else args.count

    # ---- 加载种子数据 ----
    seed_examples: Dict[str, List[Dict]] = {}
    if args.seed_file:
        with open(args.seed_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                s = json.loads(line)
                lbl = s.get("sarcasm_label", s.get("label", ""))
                seed_examples.setdefault(lbl, []).append(s)
        total_seeds = sum(len(v) for v in seed_examples.values())
        print(f"已加载种子数据: {total_seeds} 条")

    # ---- 断点续传 ----
    resume_counts: Dict[str, int] = {}
    if args.resume and os.path.exists(args.output):
        existing = IncrementalWriter(args.output).get_existing_bridge_labels()
        for bl in bridge_labels:
            bl_name = bl["bridge_label"]
            already = existing.get(bl_name, 0)
            target = get_count_per_label(bl["bridge_type"])
            need = max(0, target - already)
            resume_counts[bl_name] = need
            if need == 0:
                print(f"[{bl_name}] 已完成 ({already}/{target})，跳过")
            else:
                print(f"[{bl_name}] 已有 {already}，还需 {need}")
    else:
        for bl in bridge_labels:
            resume_counts[bl["bridge_label"]] = get_count_per_label(bl["bridge_type"])

    total_need = sum(resume_counts.values())
    if total_need == 0:
        print("所有桥接标签已完成，无需生成。")
        return

    # ---- 初始化生成器 ----
    generator = BridgeDataGenerator(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
    )

    print(f"\nAPI 端点: {args.base_url}/v1/messages")
    print(f"模型: {args.model}")
    print(f"输出文件: {args.output}")
    print(f"桥接类型: {bridge_types}")
    print(f"下游任务: {task_ids}")
    print(f"桥接标签数: {len(bridge_labels)}, 总目标: {total_need} 条")
    print(f"{'='*60}\n")

    # ---- 逐标签生成 ----
    t0 = time.time()
    grand_total = 0
    pending_buffer: List[Dict] = []

    with IncrementalWriter(args.output) as writer:
        for bl_info in bridge_labels:
            bl_name = bl_info["bridge_label"]
            need = resume_counts.get(bl_name, 0)
            if need <= 0:
                continue

            print(f"\n{'='*60}")
            print(f"[{bl_name}] "
                  f"分类={bl_info['sarcasm_label']} "
                  f"任务={bl_info['task_id']} "
                  f"桥接型={bl_info['bridge_type']} "
                  f"→ 目标 {need} 条")
            print(f"{'='*60}")

            def make_callback():
                def callback(batch: List[Dict]):
                    nonlocal grand_total, pending_buffer
                    pending_buffer.extend(batch)
                    grand_total += len(batch)
                    flush_every = args.flush_every or args.batch_size
                    if len(pending_buffer) >= flush_every:
                        writer.write_batch(pending_buffer)
                        pending_buffer.clear()
                return callback

            seeds = seed_examples.get(bl_info["sarcasm_label"], []) if seed_examples else []
            _ = generator.generate_batch(
                bridge_label_info=bl_info,
                count=need,
                seed_examples=seeds,
                batch_size=args.batch_size,
                on_batch=make_callback(),
            )

        # 兜底落库
        if pending_buffer:
            writer.write_batch(pending_buffer)
            pending_buffer.clear()

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"全部完成！共 {writer.count} 条，耗时 {elapsed:.0f}s "
          f"({writer.count/elapsed:.1f} 条/s)" if elapsed > 0 else "")
    print(f"输出文件: {args.output}")
    print(f"{'='*60}")

    # ---- 质量验证 ----
    if args.validate:
        print(f"\n{'='*60}")
        print("质量检查...")
        print(f"{'='*60}")
        issues_found = 0
        with open(args.output, "r", encoding="utf-8") as f:
            all_samples = [json.loads(line) for line in f if line.strip()]

        by_bl: Dict[str, List[Dict]] = {}
        for s in all_samples:
            lbl = s.get("bridge_label", s.get("label", "__unknown__"))
            by_bl.setdefault(lbl, []).append(s)

        for bl_name, samples in sorted(by_bl.items()):
            passed = warned = failed = 0
            for s in samples:
                result = check_bridge_cot_quality(s)
                if not result["passed"]:
                    failed += 1
                    if issues_found < 5:
                        print(f"  [FAIL] {bl_name}: {result['issues']}")
                    issues_found += 1
                elif result["warnings"]:
                    warned += 1
                    if issues_found < 5:
                        print(f"  [WARN] {bl_name}: {result['warnings']}")
                else:
                    passed += 1
            print(f"  [{bl_name}] 通过:{passed} 警告:{warned} 失败:{failed}")

        print(f"\n  总计问题: {issues_found}")


if __name__ == "__main__":
    main()
