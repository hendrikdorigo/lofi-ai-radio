"""
Presets de "mood" (estilo) da rádio — define os prompts de música e de
imagem de fundo pra cada variante do canal.

Adicionar um novo mood é só adicionar uma entrada no dicionário MOODS.
"""

MOODS = {
    "lofi_classical": {
        "nome": "Classical Lofi",
        "prompts_musica": [
            (
                "lofi hip hop beat blended with a baroque piano theme in the style of "
                "Bach, mellow, warm vinyl crackle, soft drums, relaxing study music, "
                "no vocals"
            ),
            (
                "lofi chillhop with a romantic-era string melody inspired by Chopin, "
                "gentle piano, dusty vinyl texture, slow tempo, calm and melancholic, "
                "no vocals"
            ),
            (
                "lofi beat with a classical string quartet motif in the style of "
                "Vivaldi, soft jazzy chords, tape hiss, cozy late-night study "
                "atmosphere, no vocals"
            ),
            (
                "lofi hip hop with a delicate classical flute and harp melody, "
                "warm analog texture, slow relaxed drums, dreamy and nostalgic, "
                "no vocals"
            ),
        ],
        "prompt_fundo": (
            "cozy candlelit study room at night, classical piano and old books, "
            "warm lamp light, rain on the window, painterly illustration, "
            "vertical 9:16 composition, no text, no watermark, no people"
        ),
        "titulo_live": "Classical Lofi 24/7 🎻📚 AI-Generated Study Music Radio",
        "descricao_live": (
            "A continuous lofi radio inspired by classical music, entirely "
            "composed by AI — perfect for studying, working, or relaxing.\n\n"
            "#lofi #classicalmusic #studymusic #lofihiphop #chillbeats"
        ),
    },
    "lofi_medieval": {
        "nome": "Lofi Medieval",
        "prompts_musica": [
            (
                "lofi hip hop beat blended with medieval lute and hand drum melody, "
                "tavern atmosphere, warm vinyl crackle, slow relaxed tempo, no vocals"
            ),
            (
                "lofi chillhop with a medieval harp and flute theme, castle at night "
                "ambience, soft dusty texture, calm and mysterious, no vocals"
            ),
            (
                "lofi beat with medieval bard-style acoustic guitar and strings, "
                "fireplace crackling underneath, cozy tavern mood, no vocals"
            ),
            (
                "lofi hip hop with medieval choir pads and hurdy-gurdy melody, "
                "slow tempo, warm analog texture, nostalgic and peaceful, no vocals"
            ),
        ],
        "prompt_fundo": (
            "cozy medieval tavern interior at night, fireplace, wooden tables, "
            "candlelight, lute hanging on the wall, painterly illustration, "
            "vertical 9:16 composition, no text, no watermark, no people"
        ),
        "titulo_live": "Medieval Lofi 24/7 🏰🔥 AI-Generated Tavern Radio",
        "descricao_live": (
            "A continuous lofi radio inspired by medieval music, entirely "
            "composed by AI — cozy tavern vibes for studying, working, or "
            "relaxing.\n\n#lofi #medieval #studymusic #tavernmusic #chillbeats"
        ),
    },
    "classic_rock": {
        "nome": "Classic Rock 24/7",
        "prompts_musica": [
            (
                "instrumental classic rock track, 1970s style, energetic electric "
                "guitar riffs, driving drums, bluesy guitar solo, warm analog "
                "studio sound, no vocals"
            ),
            (
                "instrumental hard rock jam, gritty distorted guitar, powerful "
                "steady drumbeat, bass-driven groove, arena rock energy, no vocals"
            ),
            (
                "instrumental blues rock track, slow burning electric guitar lead, "
                "shuffle drum groove, smoky bar atmosphere, expressive and raw, "
                "no vocals"
            ),
            (
                "instrumental southern rock track, twangy slide guitar, upbeat "
                "groove, live-band energy, warm vintage recording texture, "
                "no vocals"
            ),
        ],
        "prompt_fundo": (
            "vintage rock concert stage at night, electric guitars and amplifiers, "
            "dramatic stage lighting, smoke haze, retro 1970s aesthetic, painterly "
            "illustration, vertical 9:16 composition, no text, no watermark, no people"
        ),
        "titulo_live": "Classic Rock 24/7 🎸🔥 AI-Generated Instrumental Rock Radio",
        "descricao_live": (
            "A continuous instrumental classic rock radio, entirely composed "
            "by AI — guitar riffs, drums, and non-stop groove.\n\n"
            "#classicrock #rock #instrumental #radio247"
        ),
    },
}


def obter_mood(nome: str) -> dict:
    if nome not in MOODS:
        disponiveis = ", ".join(MOODS)
        raise ValueError(f"Mood '{nome}' não existe. Disponíveis: {disponiveis}")
    return MOODS[nome]
