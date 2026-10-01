"""各 dialogue cut に対する 漫画吹き出し設定.

shape: "oval" (普通会話 - 楕円白吹き出し + 尻尾) のみ
position: "auto" (顔検出 heuristic で自動)
        / "tl" (top-left) / "tr" (top-right) / "tc" (top-center)
        / "bl" (bottom-left) / "br" (bottom-right) / "bc" (bottom-center)

外部素材 (illustcenter) は破棄。 PIL で動的に 白楕円+尻尾 を描画。
キャラ顔回避は compose 段の detect_empty_quadrant heuristic で自動決定。
"""

BUBBLES = {
    # ===== P1 =====
    "C012": {"shape": "oval", "position": "auto"},  # char_a excited
    "C004": {"shape": "oval", "position": "auto"},  # char_a pleading cont
    "C005": {"shape": "oval", "position": "auto"},  # char_b sarcastic

    # ===== P2 =====
    "C008": {"shape": "oval", "position": "auto"},  # char_a excited
    "C010": {"shape": "oval", "position": "auto"},  # char_a proud thumbs
    "C012": {"shape": "oval", "position": "auto"},  # char_b bored
    "C013": {"shape": "oval", "position": "auto"},  # char_b probe
    "C014": {"shape": "oval", "position": "auto"},  # char_a innocent
    "C015": {"shape": "oval", "position": "auto"},  # char_b sigh

    # ===== P3 =====
    "C016": {"shape": "oval", "position": "auto"},  # char_a sad
    "C017": {"shape": "oval", "position": "auto"},  # char_a sad cont
    "C019": {"shape": "oval", "position": "auto"},  # char_a awkward
    "C020": {"shape": "oval", "position": "auto"},  # char_a awkward cont
    "C022": {"shape": "oval", "position": "auto"},  # char_a puzzled
}
