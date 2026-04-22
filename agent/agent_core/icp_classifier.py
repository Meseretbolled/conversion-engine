from dataclasses import dataclass
from typing import Optional

SEGMENT_NAMES = {1:"Recently-funded Series A/B",2:"Mid-market restructuring",3:"Engineering-leadership transition",4:"Specialized capability gap"}
PITCH_VARIANTS = {(1,True):"scale_ai_team",(1,False):"first_ai_function",(2,True):"offshore_ai_cost",(2,False):"offshore_cost",(3,None):"leadership_reassessment",(4,None):"ml_project_consulting"}

@dataclass
class ICPResult:
    segment: Optional[int]
    segment_name: str
    confidence: float
    confidence_label: str
    rationale: str
    disqualified: bool = False
    disqualification_reason: str = ""
    pitch_variant: str = ""

    def to_dict(self):
        return {"segment":self.segment,"segment_name":self.segment_name,"confidence":self.confidence,
            "confidence_label":self.confidence_label,"rationale":self.rationale,
            "disqualified":self.disqualified,"disqualification_reason":self.disqualification_reason,
            "pitch_variant":self.pitch_variant}

def classify(hiring_signal_brief: dict) -> ICPResult:
    fs = hiring_signal_brief.get("funding_signal") or {}
    am = hiring_signal_brief.get("ai_maturity") or {}
    icp_signals = hiring_signal_brief.get("icp_segment_signals", [])
    ai_score = am.get("score", 0)
    ai_confidence = am.get("confidence", "low")
    ai_high = ai_score >= 2

    seg3 = _find(icp_signals, 3)
    if seg3:
        return ICPResult(segment=3, segment_name=SEGMENT_NAMES[3],
            confidence=_c(seg3["confidence"]), confidence_label=seg3["confidence"],
            rationale=seg3["rationale"], pitch_variant=PITCH_VARIANTS[(3,None)])

    seg2 = _find(icp_signals, 2)
    if seg2:
        if fs.get("is_recent") and fs.get("is_series_ab"):
            return ICPResult(segment=2, segment_name=SEGMENT_NAMES[2], confidence=0.55,
                confidence_label="medium",
                rationale=seg2["rationale"]+" NOTE: conflicting funding signal — verify segment.",
                pitch_variant=PITCH_VARIANTS[(2,ai_high)])
        return ICPResult(segment=2, segment_name=SEGMENT_NAMES[2],
            confidence=_c(seg2["confidence"]), confidence_label=seg2["confidence"],
            rationale=seg2["rationale"], pitch_variant=PITCH_VARIANTS[(2,ai_high)])

    seg1 = _find(icp_signals, 1)
    if seg1:
        return ICPResult(segment=1, segment_name=SEGMENT_NAMES[1],
            confidence=_c(seg1["confidence"]), confidence_label=seg1["confidence"],
            rationale=seg1["rationale"], pitch_variant=PITCH_VARIANTS[(1,ai_high)])

    if ai_score >= 2:
        return ICPResult(segment=4, segment_name=SEGMENT_NAMES[4],
            confidence=_c(ai_confidence), confidence_label=ai_confidence,
            rationale=f"AI maturity score {ai_score}/3 ({ai_confidence} confidence). {am.get('summary','')}",
            pitch_variant=PITCH_VARIANTS[(4,None)])

    return ICPResult(segment=None, segment_name="Unqualified", confidence=0.0,
        confidence_label="low", rationale="No qualifying signal found in public data.",
        disqualified=True, disqualification_reason="No ICP signal")

def _find(signals, segment):
    return next((s for s in signals if s.get("segment") == segment), None)

def _c(label):
    return {"low":0.35,"medium":0.65,"high":0.85}.get(label, 0.5)
