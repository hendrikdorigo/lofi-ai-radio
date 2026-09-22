#!/usr/bin/env bash
# Reconstroi a playlist a partir de qualquer gravação/mid novo em
# assets/gravacoes_fonte/ ou assets/midi_fonte/, e reinicia a live pra ela
# pegar a playlist atualizada. Rodado semanalmente pelo
# lofi-radio-refresh.timer — não precisa mexer manualmente.
set -euo pipefail

APP_DIR="/opt/lofi-ai-radio"
PY="$APP_DIR/.venv/bin/python"
MOOD="classical"

cd "$APP_DIR/scripts"

# Ambas as etapas só processam arquivos que ainda não têm faixa no catálogo
# (são incrementais), então rodar toda semana sem novidade não faz nada.
if [ -n "$(find "$APP_DIR/assets/gravacoes_fonte/$MOOD" -maxdepth 1 \
        \( -iname '*.mp3' -o -iname '*.flac' -o -iname '*.wav' -o -iname '*.ogg' -o -iname '*.m4a' \) \
        -print -quit 2>/dev/null)" ]; then
    "$PY" 01c_import_real_recordings.py --mood "$MOOD"
fi
if compgen -G "$APP_DIR/assets/midi_fonte/$MOOD/*.mid" > /dev/null; then
    "$PY" 01b_generate_faithful_tracks.py --mood "$MOOD"
fi

"$PY" 03_montar_playlist.py --mood "$MOOD"

systemctl restart lofi-radio.service
