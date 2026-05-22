from __future__ import annotations
from pydantic import BaseModel, Field

class LoginRequest(BaseModel):
    username: str = Field(..., description="学号/用户名")
    password: str = Field(..., description="密码")

class StudentLoginRequest(LoginRequest):
    pass

class TeacherLoginRequest(LoginRequest):
    pass
