"""Backends de separação.

- ``demucs_backend``: Demucs (htdemucs / htdemucs_6s) para os stems principais.
- ``roformer_backend``: modelos RoFormer via ``audio-separator`` (vocal e lead/backing).
- ``dsp``: separação fina por análise estéreo e frequência (guitarras e bateria).

Todo backend recebe/devolve ``np.ndarray`` float32 ``(2, amostras)`` em 44.1 kHz
e aceita um callback ``progress(fração 0..1)``.
"""

from typing import Callable

ProgressFn = Callable[[float], None]


def no_progress(_: float) -> None:
    pass


def tqdm_reporter(progress: ProgressFn):
    """Cria um substituto de ``tqdm(iteravel)`` que reporta a fração concluída.

    Os modelos (Demucs, audio-separator) mostram progresso com tqdm no
    terminal; trocando o tqdm deles por este, o progresso vai para a interface.
    """

    def fake_tqdm(iterable=None, *args, **kwargs):
        if iterable is None:  # usado como barra de download (total=...): ignora
            return _SilentBar()
        items = list(iterable)
        total = max(1, len(items))

        def gen():
            for i, item in enumerate(items):
                yield item
                progress((i + 1) / total)

        return gen()

    return fake_tqdm


class _SilentBar:
    def update(self, *_):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass
