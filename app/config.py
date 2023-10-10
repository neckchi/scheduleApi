from pydantic import SecretStr
from pydantic_settings import BaseSettings,SettingsConfigDict
# from dotenv import load_dotenv

# load_dotenv()
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='./app/.env', env_file_encoding='utf-8')
    # model_config = SettingsConfigDict(secrets_dir='/run/secrets')
    mongo_url: SecretStr
    #redis_host:SecretStr
    #redis_port:SecretStr
    #redis_db:SecretStr
    #redis_user:SecretStr
    #redis_pw:SecretStr
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

    #
    # class Config:
    #     # env_file = "app\.env"
    #     env_file = "./app/.env"
