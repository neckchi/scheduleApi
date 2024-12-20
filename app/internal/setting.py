from functools import cache

import yaml
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='./app/.env', env_file_encoding='utf-8')
    # model_config = SettingsConfigDict(secrets_dir='/run/secrets')
    redis_host: SecretStr
    redis_port: SecretStr
    redis_db: SecretStr
    redis_user: SecretStr
    redis_pw: SecretStr
    cma_url: str
    cma_token: SecretStr
    sudu_url: str
    sudu_token: SecretStr
    hmm_url: str
    hmm_token: SecretStr
    iqax_url: str
    iqax_token: SecretStr
    maeu_p2p: str
    maeu_location: str
    maeu_cutoff: str
    maeu_token: SecretStr
    maeu_token2: SecretStr
    oney_url: str
    oney_turl: str
    oney_token: SecretStr
    oney_auth: SecretStr
    zim_url: str
    zim_turl: str
    zim_token: SecretStr
    zim_client: SecretStr
    zim_secret: SecretStr
    mscu_url: str
    mscu_aud: str
    mscu_oauth: str
    mscu_client: SecretStr
    mscu_thumbprint: SecretStr
    mscu_scope: SecretStr
    mscu_rsa_key: SecretStr
    hlcu_url: str
    hlcu_client_id: SecretStr
    hlcu_client_secret: SecretStr
    basic_user: SecretStr
    basic_pw: SecretStr


@cache
def get_settings():
    """
    Reading a file from disk is normally a costly (slow) operation
    so we  want to do it only once and then re-use the same settings object, instead of reading it for each request.
    And this is exactly why we need to use python in built wrapper functions - cache for caching the carrier credential
    """
    return Settings()


@cache
def load_yaml() -> dict:
    with open(file='./app/configmap.yaml', mode='r') as yml_file:
        config = yaml.load(yml_file, Loader=yaml.FullLoader)
    return config
