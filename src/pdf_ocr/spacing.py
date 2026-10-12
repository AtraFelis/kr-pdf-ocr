"""공백 외 글자를 보존하는 선택적 Kiwi 띄어쓰기 보정을 제공한다."""

import re


class LocalSpacingRepair:
    """Local suggestions constrained to whitespace-only edits."""

    def __init__(self):
        """실행 중 다운로드 없이 설치된 Kiwi 모델을 단일 작업자로 초기화한다."""
        from kiwipiepy import Kiwi

        self.kiwi = Kiwi(num_workers=1)

    def repair(self, result: dict) -> dict:
        """복원된 문단의 공백만 보정하고 변경 전후 제안을 기록한다.

        Args:
            result: geometry_applied, paragraphs, reviews를 포함한 문단 복원 결과.

        Returns:
            좌표 복원 결과에는 새 문단·제안을 포함한 사전을 반환한다.
            좌표를 적용하지 않은 결과는 기존 문단 보존을 위해 그대로 반환한다.

        Raises:
            ValueError: Kiwi가 공백 외의 원문 글자를 변경한 경우.
        """
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
