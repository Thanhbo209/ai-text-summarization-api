from app.core.config import get_settings


def test_env_injection():
    get_settings.cache_clear()
    s = get_settings()
    
    assert s.gemini_model == "gemini-3.5-flash-lite"
    assert bool(s.gemini_api_key) == True
    assert s.llm_timeout_seconds == 30.0
    assert bool(s.gemini_api_base_url) == True
    assert bool(s.api_key) == True
