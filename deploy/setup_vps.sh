#!/usr/bin/env bash
# Provisiona uma VPS Ubuntu/Debian do zero pra rodar a live 24/7.
# Rode uma vez só, como root ou com sudo, depois de dar `git clone` do repo.
#
# Uso:
#   ssh root@SEU_IP
#   git clone https://github.com/hendrikdorigo/lofi-ai-radio.git /opt/lofi-ai-radio
#   cd /opt/lofi-ai-radio
#   bash deploy/setup_vps.sh
set -euo pipefail

APP_DIR="/opt/lofi-ai-radio"
SERVICE_USER="lofiradio"

if [ "$(id -u)" -ne 0 ]; then
    echo "Rode como root (ou com sudo)." >&2
    exit 1
fi

echo "==> Instalando dependências do sistema (ffmpeg, fluidsynth, python3-venv)..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip ffmpeg fluidsynth ca-certificates curl

# fluidsynth só é usado pela etapa 1b (fallback opcional, MIDI sintetizado
# pra peças que você não achar como gravação real). A via principal (1c,
# gravações reais) só precisa do ffmpeg acima.
SOUNDFONT_PATH="$APP_DIR/assets/soundfont/FluidR3_GM.sf2"
mkdir -p "$APP_DIR/assets/soundfont"
echo "==> (Opcional) Soundfont pra etapa 1b: se for usar, baixe manualmente um"
echo "    GM (.sf2) de uma fonte confiável e suba pra:"
echo "    $SOUNDFONT_PATH"
echo "    (ex: scp FluidR3_GM.sf2 root@SEU_IP:$SOUNDFONT_PATH)"

echo "==> Criando usuário de serviço sem privilégios ($SERVICE_USER)..."
id -u "$SERVICE_USER" &>/dev/null || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

echo "==> Criando venv e instalando dependências Python..."
sudo -u "$SERVICE_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/config/.env" ]; then
    echo "==> Copiando config/.env.example -> config/.env (edite antes de continuar!)"
    sudo -u "$SERVICE_USER" cp "$APP_DIR/config/.env.example" "$APP_DIR/config/.env"
    sudo -u "$SERVICE_USER" sed -i "s|^SOUNDFONT_PATH=.*|SOUNDFONT_PATH=$SOUNDFONT_PATH|" "$APP_DIR/config/.env"
fi

echo "==> Instalando serviços systemd..."
cp "$APP_DIR/deploy/lofi-radio.service" /etc/systemd/system/lofi-radio.service
cp "$APP_DIR/deploy/lofi-radio-refresh.service" /etc/systemd/system/lofi-radio-refresh.service
cp "$APP_DIR/deploy/lofi-radio-refresh.timer" /etc/systemd/system/lofi-radio-refresh.timer
systemctl daemon-reload
systemctl enable lofi-radio-refresh.timer
systemctl start lofi-radio-refresh.timer

cat <<'EOF'

==> Pronto. Próximos passos manuais:

1. Edite /opt/lofi-ai-radio/config/.env e preencha:
     - YOUTUBE_STREAM_KEY (studio.youtube.com > Criar > Ir ao vivo)
     - IDEOGRAM_API_KEY   (pra gerar o fundo, uma vez)
   O SOUNDFONT_PATH já foi preenchido automaticamente.

2. Coloque suas gravações reais (baixadas de musopen.org, licença Public
   Domain ou CC0) em:
     /opt/lofi-ai-radio/assets/gravacoes_fonte/classical/*.mp3
   (fallback opcional: .mid de mutopiaproject.org em
   assets/midi_fonte/classical/, se não achar gravação real de alguma peça)

3. Rode a preparação inicial (gera fundo + playlist), uma vez:
     sudo -u lofiradio /opt/lofi-ai-radio/.venv/bin/python \
       /opt/lofi-ai-radio/scripts/01c_import_real_recordings.py --mood classical
     sudo -u lofiradio /opt/lofi-ai-radio/.venv/bin/python \
       /opt/lofi-ai-radio/scripts/02_generate_background.py --mood classical
     sudo -u lofiradio /opt/lofi-ai-radio/.venv/bin/python \
       /opt/lofi-ai-radio/scripts/03_montar_playlist.py --mood classical

4. Suba a live:
     systemctl enable --now lofi-radio.service

5. Acompanhe:
     systemctl status lofi-radio.service
     journalctl -u lofi-radio.service -f

Dali em diante ela reinicia sozinha (queda de rede, reboot da VPS, etc.) e o
timer semanal (lofi-radio-refresh.timer) reconstrói a playlist com qualquer
gravação ou .mid novo que você jogar em assets/gravacoes_fonte/classical/ ou
assets/midi_fonte/classical/ via scp.
EOF
