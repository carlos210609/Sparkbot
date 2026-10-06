from __future__ import annotations
FORBIDDEN_MARKERS=("fake account","fake accounts","buy followers","fake likes","fake traffic","ad clicking","captcha bypass","kyc bypass","steal credentials","password collection","unauthorized exploit","spam blast","metric manipulation")

def validate_request(text:str)->tuple[bool,str]:
 lower=text.lower()
 for marker in FORBIDDEN_MARKERS:
  if marker in lower:return False,f"blocked by safety policy: {marker}"
 return True,"allowed"
