from __future__ import annotations

import pytest


def test_english_g2p_rebuilds_missing_dict_cache(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from KGTS.core.tts_service import _prepare_genie_import_path, _prepare_genie_runtime, get_tts_settings

    _prepare_genie_runtime(get_tts_settings())
    _prepare_genie_import_path()
    from genie_tts.G2P.English import EnglishG2P

    cache_path = tmp_path / "engdict_cache.pickle"
    monkeypatch.setattr(EnglishG2P, "CACHE_PATH", str(cache_path))
    monkeypatch.setattr(EnglishG2P.os.path, "exists", lambda path: path != EnglishG2P.CACHE_PATH)
    monkeypatch.setattr(
        EnglishG2P,
        "_read_cmu_dict",
        lambda path: {"hardy": [["HH", "AA1", "R", "D", "IY0"]]} if path != EnglishG2P.CMU_DICT_HOT_PATH else {},
    )

    loaded = EnglishG2P._load_and_cache_dict()

    assert loaded["hardy"][0] == ["HH", "AA1", "R", "D", "IY0"]


def test_english_g2p_strips_terminal_punctuation_before_predicting(monkeypatch: pytest.MonkeyPatch) -> None:
    from KGTS.core.tts_service import _prepare_genie_import_path, _prepare_genie_runtime, get_tts_settings

    _prepare_genie_runtime(get_tts_settings())
    _prepare_genie_import_path()
    from genie_tts.G2P.English import EnglishG2P

    g2p = EnglishG2P.CleanG2p.__new__(EnglishG2P.CleanG2p)
    g2p.cmu = {"equilibrium": [["IY2", "K", "W", "AH0"]]}
    g2p.namedict = {}
    g2p.homograph2features = {}
    monkeypatch.setattr(g2p, "predict", lambda word: (_ for _ in ()).throw(AssertionError("predict should not run")))

    assert g2p._query_word("equilibrium。") == ["IY2", "K", "W", "AH0"]


def test_tts_player_propagates_worker_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from KGTS.core.tts_service import _prepare_genie_import_path, _prepare_genie_runtime, get_tts_settings

    _prepare_genie_runtime(get_tts_settings())
    _prepare_genie_import_path()
    from genie_tts.Core.TTSPlayer import TTSPlayer
    from genie_tts.Core import TTSPlayer as tts_player_module

    class _FakeModel:
        T2S_ENCODER = object()
        T2S_FIRST_STAGE_DECODER = object()
        T2S_STAGE_DECODER = object()
        VITS = object()
        PROMPT_ENCODER = None
        LANGUAGE = "Chinese"

    player = TTSPlayer()
    values = iter(["bad input", None])
    player._text_queue.get = lambda timeout=None: next(values)
    monkeypatch.setattr(player._stop_event, "is_set", lambda: False)
    monkeypatch.setattr(tts_player_module.model_manager, "get", lambda speaker: _FakeModel())
    monkeypatch.setattr(tts_player_module.context, "current_speaker", "shu")
    monkeypatch.setattr(tts_player_module.context, "current_prompt_audio", object())
    monkeypatch.setattr(tts_player_module.tts_client, "tts", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("worker boom")))

    player._tts_worker_loop()

    with pytest.raises(RuntimeError, match="worker boom"):
        player.wait_for_tts_completion()
