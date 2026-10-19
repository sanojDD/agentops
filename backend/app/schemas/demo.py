from pydantic import BaseModel


class DemoStatus(BaseModel):
    enabled: bool
    questions_left_today: int = 0
    max_question_chars: int = 0
    session_minutes: int = 0


class DemoSession(BaseModel):
    token: str
    expires_at: str
    questions_left_today: int
    max_question_chars: int
