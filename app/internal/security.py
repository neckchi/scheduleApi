import logging
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.internal.setting import get_settings

security = HTTPBasic()


def basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
	current_username_bytes = credentials.username.encode("utf8")
	correct_username_bytes = bytes(get_settings().basic_user.get_secret_value(), encoding='utf-8')
	is_correct_username = secrets.compare_digest(
		current_username_bytes, correct_username_bytes
	)
	current_password_bytes = credentials.password.encode("utf8")
	correct_password_bytes = bytes(get_settings().basic_pw.get_secret_value(), encoding='utf-8')
	is_correct_password = secrets.compare_digest(
		current_password_bytes, correct_password_bytes
	)
	if not (is_correct_username and is_correct_password):
		logging.error('User cant access to API hub due to wrong user id and password')
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Incorrect email or password",
			headers={"WWW-Authenticate": "Basic"},
		)
	return credentials.username
