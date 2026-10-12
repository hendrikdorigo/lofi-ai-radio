"""Catálogo de stems: nome interno, rótulo em português, grupo e cor.

O nome interno vira nome de arquivo (``<nome>.wav``) e identificador na API.
O grupo é usado pelo frontend para os presets de Karaokê/Play-along
(ex.: "mutar todas as guitarras").
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StemInfo:
    name: str
    label: str
    group: str  # voz | guitarra | baixo | bateria | teclado | outros
    color: str
    description: str = ""


_CATALOG = [
    StemInfo("vocal", "Voz", "voz", "#f472b6", "Todas as vozes"),
    StemInfo("vocal_principal", "Voz principal", "voz", "#f472b6", "Lead vocal"),
    StemInfo("backing_vocals", "Backing vocals", "voz", "#c084fc", "Coros, harmonias e gritos"),
    StemInfo("guitarra", "Guitarra", "guitarra", "#fb923c", "Todas as guitarras"),
    StemInfo(
        "guitarra_solo",
        "Guitarra solo",
        "guitarra",
        "#f97316",
        "Melodia principal — no dueto, a voz mais aguda (estimativa)",
    ),
    StemInfo(
        "guitarra_dueto",
        "Guitarra dueto (2ª voz)",
        "guitarra",
        "#ef4444",
        "Segunda melodia tocada junto com o solo, em harmonia (estimativa)",
    ),
    StemInfo("guitarra_base", "Base centro", "guitarra", "#fdba74", "Base/acordes no centro do estéreo (estimativa)"),
    StemInfo("guitarra_1", "Base esquerda", "guitarra", "#facc15", "Base/acordes do lado esquerdo (estimativa)"),
    StemInfo("guitarra_2", "Base direita", "guitarra", "#eab308", "Base/acordes do lado direito (estimativa)"),
    StemInfo("baixo", "Baixo", "baixo", "#4ade80"),
    StemInfo("bateria", "Bateria", "bateria", "#60a5fa"),
    StemInfo("bumbo", "Bumbo", "bateria", "#3b82f6", "Estimativa por faixa de frequência"),
    StemInfo("caixa", "Caixa e tons", "bateria", "#38bdf8", "Estimativa por faixa de frequência"),
    StemInfo("pratos", "Pratos", "bateria", "#93c5fd", "Estimativa por faixa de frequência"),
    StemInfo("teclado", "Teclado / piano", "teclado", "#2dd4bf"),
    StemInfo("outros", "Outros", "outros", "#a3a3a3", "Tudo que não se encaixou nos outros stems"),
]

CATALOG: dict[str, StemInfo] = {s.name: s for s in _CATALOG}

# Ordem de exibição no player.
ORDER = [s.name for s in _CATALOG]

# Mapeia nomes de saída do Demucs para os nomes do StemSplit.
DEMUCS_NAMES = {
    "vocals": "vocal",
    "drums": "bateria",
    "bass": "baixo",
    "other": "outros",
    "guitar": "guitarra",
    "piano": "teclado",
}


def describe(names: list[str]) -> list[dict]:
    """Devolve a lista de stems em ordem de exibição, com metadados."""
    ordered = sorted(names, key=lambda n: ORDER.index(n) if n in ORDER else len(ORDER))
    return [asdict(CATALOG[n]) if n in CATALOG else asdict(StemInfo(n, n, "outros", "#a3a3a3")) for n in ordered]
