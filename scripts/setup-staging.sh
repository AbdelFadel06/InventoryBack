#!/usr/bin/env bash
# Installe ou met à jour une instance de ShopM à côté de la prod, sans y toucher :
#   - le staging (par défaut) : tests, comptes @shopm.test ;
#   - la démo publique (INSTANCE=demo) : boutique fictive, mode démo, remise à zéro chaque nuit.
#
# Écrit uniquement dans : /var/www/shopm-<instance>, la base shopm_<instance>, le service
# shopm-<instance> et son site nginx. La prod n'est que lue (adresse des dépôts).
#
# À lancer sur le VPS avec un utilisateur qui a sudo (pas en root) :
#   bash setup-staging.sh [branche-backend] [branche-frontend]
#   INSTANCE=demo bash setup-staging.sh main main
# Relancer le script déploie les branches indiquées sur l'instance.
set -euo pipefail

INSTANCE="${INSTANCE:-staging}"
case "$INSTANCE" in
  staging) PORT="8100" ;;
  demo)    PORT="8200" ;;
  *) printf 'INSTANCE inconnue : %s (staging ou demo)\n' "$INSTANCE" >&2; exit 1 ;;
esac
DOMAIN="shopm-$INSTANCE.abdelsaliou.dev"
PROD_DOMAIN="shopm.abdelsaliou.dev"
ROOT="/var/www/shopm-$INSTANCE"
SERVICE="shopm-$INSTANCE"
SYSTEM_USER="shopm-$INSTANCE"
DB_NAME="shopm_$INSTANCE"
DB_USER="shopm_${INSTANCE}_user"
# Mot de passe PUBLIC des comptes de la démo (affiché sur la landing) : aucune donnée réelle derrière.
DEMO_PASSWORD="${DEMO_PASSWORD:-Demo-ShopM-2026!}"
PROD_BACKEND="/var/www/shopm/backend"
PROD_FRONTEND="/var/www/shopm/frontend"
BACKEND_BRANCH="${1:-main}"
FRONTEND_BRANCH="${2:-main}"

BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
ENV_FILE="$BACKEND_DIR/.env"
PYTHON="$ROOT/venv/bin/python"
NGINX_AVAILABLE="/etc/nginx/sites-available/$SERVICE"
NGINX_ENABLED="/etc/nginx/sites-enabled/$SERVICE"
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
FIRST_INSTALL="no"

step() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERREUR : %s\n' "$*" >&2; exit 1; }

check_prerequisites() {
  step "Vérifications"
  [[ "$EUID" -ne 0 ]] || die "lance ce script avec ton utilisateur, pas en root."

  local staging_ip prod_ip
  staging_ip="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1 {print $1}')"
  prod_ip="$(getent ahostsv4 "$PROD_DOMAIN" | awk 'NR==1 {print $1}')"
  [[ -n "$staging_ip" ]] || die "$DOMAIN ne résout pas encore : crée l'entrée DNS, puis relance."
  [[ "$staging_ip" == "$prod_ip" ]] || die "$DOMAIN pointe sur $staging_ip au lieu de $prod_ip."

  if ss -ltn | grep -q "127.0.0.1:$PORT " && ! systemctl is-active --quiet "$SERVICE"; then
    die "le port $PORT est déjà utilisé par un autre programme."
  fi
  echo "OK"
}

create_directories() {
  step "Utilisateur système et répertoires"
  if ! id "$SYSTEM_USER" >/dev/null 2>&1; then
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$SYSTEM_USER"
  fi
  sudo mkdir -p "$ROOT"
  sudo chown "$USER:$USER" "$ROOT"
  mkdir -p "$ROOT/certbot"
}

update_repo() {
  local url="$1" dir="$2" branch="$3"
  [[ -d "$dir/.git" ]] || git clone "$url" "$dir"
  git -C "$dir" fetch origin "$branch"
  git -C "$dir" checkout -q -B staging-deploy FETCH_HEAD
  git -C "$dir" reset -q --hard FETCH_HEAD
  git -C "$dir" log -1 --format="$dir : %h %s"
}

update_code() {
  step "Code : backend $BACKEND_BRANCH, frontend $FRONTEND_BRANCH"
  update_repo "$(git -C "$PROD_BACKEND" remote get-url origin)" "$BACKEND_DIR" "$BACKEND_BRANCH"
  update_repo "$(git -C "$PROD_FRONTEND" remote get-url origin)" "$FRONTEND_DIR" "$FRONTEND_BRANCH"
}

setup_database_and_env() {
  [[ ! -f "$ENV_FILE" ]] || return 0
  FIRST_INSTALL="yes"
  step "Base de données $DB_NAME et fichier .env"

  local db_password secret_key
  db_password="$(openssl rand -hex 24)"
  secret_key="$(openssl rand -hex 40)"

  sudo -u postgres psql -q -v ON_ERROR_STOP=1 <<SQL
SELECT 'CREATE ROLE $DB_USER LOGIN'
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER')\gexec
ALTER ROLE $DB_USER LOGIN PASSWORD '$db_password';
SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER'
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '$DB_NAME')\gexec
REVOKE CONNECT ON DATABASE $DB_NAME FROM PUBLIC;
GRANT CONNECT ON DATABASE $DB_NAME TO $DB_USER;
SQL

  (
    umask 077
    cat > "$ENV_FILE" <<ENV
SECRET_KEY=$secret_key
DEBUG=False
ALLOWED_HOSTS=$DOMAIN
CSRF_TRUSTED_ORIGINS=https://$DOMAIN
CORS_ALLOWED_ORIGINS=https://$DOMAIN
FRONTEND_URL=https://$DOMAIN
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$db_password
DB_HOST=localhost
DB_PORT=5432
# Aucun e-mail réel ne part de cette instance.
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
ENV
    if [[ "$INSTANCE" == "demo" ]]; then
      printf 'ALLOW_DEMO_SEED=true\nDEMO_MODE=true\nDEMO_PASSWORD=%s\n' "$DEMO_PASSWORD" >> "$ENV_FILE"
    else
      printf 'ALLOW_STAGING_SEED=true\n' >> "$ENV_FILE"
    fi
  )
  sudo chown "$USER:$SYSTEM_USER" "$ENV_FILE"
  chmod 640 "$ENV_FILE"
}

deploy_backend() {
  step "Backend : dépendances, migrations, fichiers statiques"
  [[ -x "$PYTHON" ]] || python3 -m venv "$ROOT/venv"
  "$PYTHON" -m pip install --quiet --upgrade pip
  "$PYTHON" -m pip install --quiet -r "$BACKEND_DIR/requirements.txt"

  cd "$BACKEND_DIR"
  # Clés des notifications téléphone : gardées hors du dépôt pour survivre aux réinstallations
  # (en changer désabonnerait les téléphones). Jamais affichées.
  local vapid_file="$ROOT/vapid.env"
  if ! grep -q '^VAPID_PRIVATE_KEY=' "$ENV_FILE"; then
    [[ -s "$vapid_file" ]] || (umask 077; "$PYTHON" manage.py generate_vapid_keys > "$vapid_file")
    cat "$vapid_file" >> "$ENV_FILE"
  fi
  "$PYTHON" manage.py migrate --no-input
  "$PYTHON" manage.py collectstatic --no-input --verbosity 0

  # Le service n'écrit que dans les dossiers d'images envoyées.
  mkdir -p profile_pictures shop_logos demo_data
  sudo chown -R "$SYSTEM_USER:$SYSTEM_USER" profile_pictures shop_logos demo_data
  cd - >/dev/null
}

install_service() {
  step "Service $SERVICE"
  sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null <<UNIT
[Unit]
Description=Gunicorn pour l'instance $INSTANCE de ShopM
After=network.target postgresql.service

[Service]
User=$SYSTEM_USER
Group=$SYSTEM_USER
WorkingDirectory=$BACKEND_DIR
ExecStart=$ROOT/venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:$PORT --workers 1
Restart=on-failure
MemoryHigh=300M
MemoryMax=350M
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=$BACKEND_DIR/profile_pictures $BACKEND_DIR/shop_logos

[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl daemon-reload
  sudo systemctl enable --quiet "$SERVICE"
  sudo systemctl restart "$SERVICE"
}

# Lit une variable Cloudinary : d'abord $ROOT/cloudinary.env, puis les fichiers .env de la prod.
cloudinary_value() {
  local key="$1" f v
  for f in "$ROOT/cloudinary.env" "$PROD_FRONTEND/.env.production.local" "$PROD_FRONTEND/.env.production" "$PROD_FRONTEND/.env"; do
    [[ -r "$f" ]] || continue
    v="$(grep -E "^${key}=" "$f" | tail -1 | cut -d= -f2- | tr -d '"'"'"'\r' | xargs)"
    if [[ -n "$v" ]]; then printf '%s' "$v"; return; fi
  done
}

deploy_frontend() {
  step "Frontend : compilation (plus lente, le serveur reste disponible)"
  # .env.production.local prime sur le .env du dépôt et n'est pas suivi par git.
  # Cloudinary : $ROOT/cloudinary.env s'il existe (compte ou preset dédié), sinon les réglages
  # de la prod. Les photos vont dans un dossier à part (shopm-<instance>/...). Jamais affichés.
  local cloud_name preset
  cloud_name="$(cloudinary_value VITE_CLOUDINARY_CLOUD_NAME)"
  preset="$(cloudinary_value VITE_CLOUDINARY_UPLOAD_PRESET)"
  cat > "$FRONTEND_DIR/.env.production.local" <<ENV
VITE_API_URL=https://$DOMAIN/api
VITE_CLOUDINARY_CLOUD_NAME=$cloud_name
VITE_CLOUDINARY_UPLOAD_PRESET=$preset
VITE_CLOUDINARY_FOLDER_PREFIX=shopm-$INSTANCE
ENV
  if [[ -n "$cloud_name" && -n "$preset" ]]; then
    printf '  Photos : Cloudinary actif (dossier shopm-%s)\n' "$INSTANCE"
  else
    printf '  Photos : Cloudinary non trouvé, envoi de photos désactivé\n'
  fi
  # Démo seulement : la page de connexion propose les profils démo, champs préremplis.
  if [[ "$INSTANCE" == "demo" ]]; then
    printf 'VITE_DEMO_PASSWORD=%s\n' "$DEMO_PASSWORD" >> "$FRONTEND_DIR/.env.production.local"
  fi
  cd "$FRONTEND_DIR"
  nice -n 10 npm ci --no-audit --no-fund
  NODE_OPTIONS=--max-old-space-size=768 nice -n 10 npm run build
  cd - >/dev/null
}

http_server_block() {
  cat <<NGINX
server {
    listen 80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root $ROOT/certbot;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}
NGINX
}

https_server_block() {
  cat <<NGINX

server {
    listen 443 ssl;
    server_name $DOMAIN;

    ssl_certificate $CERT_DIR/fullchain.pem;
    ssl_certificate_key $CERT_DIR/privkey.pem;

    add_header X-Robots-Tag "noindex, nofollow" always;

    location /api/ {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /django-admin/ {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /static/ {
        alias $BACKEND_DIR/staticfiles/;
    }

    location / {
        root $FRONTEND_DIR/dist;
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX
}

reload_nginx() {
  if ! sudo nginx -t 2>/dev/null; then
    sudo nginx -t || true
    sudo rm -f "$NGINX_ENABLED"
    die "configuration nginx invalide : le site de l'instance a été retiré, nginx n'a pas été rechargé."
  fi
  sudo systemctl reload nginx
}

install_nginx_site() {
  step "Site nginx et certificat HTTPS"
  sudo ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"

  if ! sudo test -f "$CERT_DIR/fullchain.pem"; then
    http_server_block | sudo tee "$NGINX_AVAILABLE" >/dev/null
    reload_nginx
    # certonly n'écrit que le nouveau certificat et ne modifie aucun site.
    sudo certbot certonly --webroot -w "$ROOT/certbot" -d "$DOMAIN" --non-interactive --keep-until-expiring
  fi

  { http_server_block; https_server_block; } | sudo tee "$NGINX_AVAILABLE" >/dev/null
  reload_nginx
}

install_demo_reset() {
  [[ "$INSTANCE" == "demo" ]] || return 0
  step "Remise à zéro de la démo chaque nuit (3 h)"
  sudo tee "/etc/systemd/system/$SERVICE-reset.service" >/dev/null <<UNIT
[Unit]
Description=Remise à zéro des données de la démo ShopM
After=postgresql.service

[Service]
Type=oneshot
User=$SYSTEM_USER
Group=$SYSTEM_USER
WorkingDirectory=$BACKEND_DIR
ExecStart=$PYTHON manage.py seed_demo --reset
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
UNIT
  sudo tee "/etc/systemd/system/$SERVICE-reset.timer" >/dev/null <<UNIT
[Unit]
Description=Remise à zéro de la démo ShopM chaque nuit

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT
  sudo systemctl daemon-reload
  sudo systemctl enable --now --quiet "$SERVICE-reset.timer"
}

seed_first_install() {
  [[ "$FIRST_INSTALL" == "yes" ]] || return 0
  if [[ "$INSTANCE" == "demo" ]]; then
    step "Données de la démo"
    (cd "$BACKEND_DIR" && "$PYTHON" manage.py seed_demo)
    printf '\nComptes démo (mot de passe public : %s) :\n  demo.manager@shopm.demo, demo.caisse@shopm.demo\n' "$DEMO_PASSWORD"
    return 0
  fi
  step "Données fictives et comptes de test"
  local password="Test-$(openssl rand -hex 8)"
  (cd "$BACKEND_DIR" && "$PYTHON" manage.py seed_staging --password "$password")
  printf '\nMot de passe commun des comptes de test (affiché une seule fois) :\n  %s\n' "$password"
}

check_result() {
  step "Vérification"
  local staging_api staging_app prod_app
  sleep 2
  staging_api="$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' "https://$DOMAIN/api/token/")"
  staging_app="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/")"
  prod_app="$(curl -s -o /dev/null -w '%{http_code}' "https://$PROD_DOMAIN/")"
  echo "Instance $INSTANCE, connexion API (400 attendu) : $staging_api"
  echo "Instance $INSTANCE, application (200 attendu)   : $staging_app"
  echo "Prod, application (200 attendu)      : $prod_app"
  [[ "$staging_api" == "400" && "$staging_app" == "200" && "$prod_app" == "200" ]] \
    || die "un des contrôles ne donne pas le résultat attendu."
  printf '\nInstance %s prête : https://%s\n' "$INSTANCE" "$DOMAIN"
}

check_prerequisites
create_directories
update_code
setup_database_and_env
deploy_backend
install_service
deploy_frontend
install_nginx_site
seed_first_install
install_demo_reset
check_result
