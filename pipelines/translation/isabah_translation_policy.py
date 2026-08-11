"""Shared final-English and name policy for the al-Isabah translation passes."""


NAME_POLICY = """FINAL NAME AND SEARCH CONSISTENCY POLICY:
- In transliterated names and titles, use plain ASCII punctuation: a straight apostrophe (') may represent ayn or hamza. Do not use curly ayn/hamza marks, macrons, dotted consonants, or other scholarly diacritics. Typographic quotation marks may still be used for English quotations.
- Prefer established English forms where they are unambiguous, including Muhammad, Khadijah, Aisha, Amina (not Amna), Mecca, and Medina.
- Keep ibn, bint, Abu, Umm, and the lowercase definite article al-. Do not silently expand a bare Arabic name to a fuller identity unless the current source context supplies that identity, and never merge distinct people merely because their short names match.
- Use these recurring work-title forms: al-Isabah, Usd al-Ghaba, al-Isti'ab, al-Tabaqat, Musnad Ahmad, al-Dhayl, and al-Tajrid.
- The structured names array must reflect the final English text and preserve the corresponding Arabic form and kind. Distinguish a spelling variant from a genuinely different identity."""
