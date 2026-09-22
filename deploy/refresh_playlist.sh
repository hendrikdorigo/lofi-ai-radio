#!/usr/bin/env bash
# Reconstroi a playlist a partir de qualquer .mid novo em assets/midi_fonte/
# e reinicia a live pra ela pegar a playlist atualizada. Rodado semanalmente
# pelo timer lofi-radio-refresh.timer — não precisa mexer manualmente.
set -euo pipefail

APP_DIR="/opt/lofi-ai-radio"
PY="$APP_DIR/.venv/bin/python"
MOOD="lofi_classical"

cd "$APP_DIR/scripts"

# 01b só processa .mid que ainda não têm faixa gerada (é incremental), então
# rodar toda semana sem novos arquivos é seguro e não faz nada.
if compgen -G "$APP_DIR/assets/midi_fonte/$MOOD/*.mid" > /dev/null; then
    "$PY" 01b_generate_faithful_tracks.py --mood "$MOOD"
fi

"$PY" 03_montar_playlist.py --mood "$MOOD"

systemctl restart lofi-radio.service
