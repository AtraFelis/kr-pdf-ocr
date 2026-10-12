import re


class LocalSpacingRepair:
    """Local suggestions constrained to whitespace-only edits."""

    def __init__(self):
        from kiwipiepy import Kiwi

        self.kiwi = Kiwi(num_workers=1)

    def repair(self, result: dict) -> dict:
        # Preserve model-generated paragraphs when line geometry is unavailable.
        if not result["geometry_applied"]:
            return result
        paragraphs = []
        reviews = list(result["reviews"])
        for index, paragraph in enumerate(result["paragraphs"]):
            before = paragraph["text"]
            after = self.kiwi.space(before, reset_whitespace=True)
            if re.sub(r"\s", "", before) != re.sub(r"\s", "", after):
                raise ValueError(
                    "띄어쓰기 보정이 원문 글자를 변경해 적용을 중단했습니다."
                )
            if before != after:
                reviews.append(
                    {
                        "paragraph_index": index,
                        "reason": "spacing_suggestion",
                        "before": before,
                        "after": after,
                    }
                )
            paragraphs.append({**paragraph, "text": after})
        return {
            **result,
            "paragraphs": paragraphs,
            "text": "\n\n".join(p["text"] for p in paragraphs),
            "reviews": reviews,
        }
