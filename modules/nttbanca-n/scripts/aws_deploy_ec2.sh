#!/usr/bin/env bash
# Despliega la API en una EC2 dentro de la misma VPC que RDS:
#   1. Rol IAM de la instancia (bucket S3, leer su configuración, Session Manager)
#   2. Configuración (.env sin access keys) en Parameter Store como SecureString
#   3. Security group de la API (HTTP 80 público) y permiso de la API hacia RDS (5432)
#   4. Instancia EC2 Ubuntu 24.04 ARM (t4g.micro)
#   5. Sube el código y lo instala o actualiza vía SSM (sin SSH ni llaves)
#   6. Prueba /health, /health/db y /health/s3 desde tu PC
#
# Requisito: haber corrido scripts/aws_setup_dev.sh (RDS, bucket y .env completo).
# Para publicar cambios del código, vuelve a correr este mismo script.
#
# Uso (en Windows, desde Git Bash):
#   bash scripts/aws_deploy_ec2.sh
#
# Variables opcionales:
#   PROJECT        prefijo de los nombres     (nttbanca)
#   INSTANCE_TYPE  tipo de instancia EC2      (t4g.micro; si cambias a x86, p. ej. t3.micro, cambia también ARCH)
#   ARCH           arquitectura de la AMI     (arm64 | amd64)

set -euo pipefail

cd "$(dirname "$0")/.."   # raíz del proyecto

PROJECT="${PROJECT:-nttbanca}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.micro}"
ARCH="${ARCH:-arm64}"

ROLE_NAME="${PROJECT}-dev-api"
API_SG_NAME="${PROJECT}-api-dev"
INSTANCE_NAME="${PROJECT}-api-dev"
ENV_PARAM="/${PROJECT}/dev/env"
TMP_DIR=".deploy-tmp"   # relativo: el CLI de Windows no entiende rutas /tmp de Git Bash

export AWS_PAGER=""
export MSYS_NO_PATHCONV=1          # que Git Bash no convierta "/nttbanca/dev/env" en una ruta de Windows
export AWS_CLI_OUTPUT_ENCODING=UTF-8   # en Windows el CLI escribe en cp1252 y rompe las tildes
export AWS_RETRY_MODE=standard
export AWS_MAX_ATTEMPTS=6

mkdir -p "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m    ! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mError: %s\033[0m\n' "$*" >&2; exit 1; }

# En Git Bash el CLI de Windows devuelve CRLF: se quita el \r para poder usar los valores.
awsq() { aws "$@" --output text | tr -d '\r'; }

# Lee una variable del .env (sin comillas ni \r)
env_get() {
  grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- | tr -d '\r' | sed -E "s/^'(.*)'$/\1/; s/^\"(.*)\"$/\1/"
}

# Agrega una regla de entrada; si ya existe, no es error.
allow_ingress() {
  local sg="$1" desc="$2" out
  shift 2
  if out=$(aws ec2 authorize-security-group-ingress --group-id "$sg" "$@" 2>&1); then
    info "$desc: agregado"
  elif [[ "$out" == *InvalidPermission.Duplicate* ]]; then
    info "$desc: ya existía"
  else
    die "$out"
  fi
}


step "Verificando .env y credenciales"
[ -f .env ] || die "No hay .env. Corre primero: bash scripts/aws_setup_dev.sh"
for var in DB_HOST DB_NAME DB_USER DB_PASSWORD S3_BUCKET_NAME AWS_REGION; do
  [ -n "$(env_get "$var")" ] || die "Falta $var en el .env."
done
REGION=$(env_get AWS_REGION)
DB_HOST=$(env_get DB_HOST)
BUCKET=$(env_get S3_BUCKET_NAME)
export AWS_DEFAULT_REGION="$REGION"

CALLER=$(awsq sts get-caller-identity --query '[Account,Arn]') \
  || die "El CLI no tiene credenciales válidas. Ejecuta 'aws configure'."
read -r ACCOUNT_ID CALLER_ARN <<< "$CALLER"
info "Cuenta:    $ACCOUNT_ID ($CALLER_ARN)"
info "Región:    $REGION"

read -r RDS_ID RDS_SG RDS_VPC < <(awsq rds describe-db-instances \
  --query 'DBInstances[].[Endpoint.Address,DBInstanceIdentifier,VpcSecurityGroups[0].VpcSecurityGroupId,DBSubnetGroup.VpcId]' \
  | awk -v host="$DB_HOST" '$1 == host { print $2, $3, $4 }') || true
[ -n "${RDS_ID:-}" ] || die "No se encontró en $REGION la instancia RDS con endpoint $DB_HOST (revisa DB_HOST en el .env)."
DEFAULT_VPC=$(awsq ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId')
[ "$RDS_VPC" = "$DEFAULT_VPC" ] \
  || die "La RDS está en $RDS_VPC y este script lanza la EC2 en la VPC por defecto ($DEFAULT_VPC)."
info "RDS:       $RDS_ID ($RDS_SG, $RDS_VPC)"
info "Bucket:    $BUCKET"


step "1/6 Rol IAM de la instancia: $ROLE_NAME"
cat > "$TMP_DIR/trust.json" <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Principal": { "Service": "ec2.amazonaws.com" }, "Action": "sts:AssumeRole" }
  ]
}
EOF
cat > "$TMP_DIR/policy.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListarBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::${BUCKET}"
    },
    {
      "Sid": "ObjetosDelBucket",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::${BUCKET}/*"
    },
    {
      "Sid": "LeerConfiguracion",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter"],
      "Resource": "arn:aws:ssm:${REGION}:${ACCOUNT_ID}:parameter${ENV_PARAM}"
    }
  ]
}
EOF
if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  info "El rol ya existe; se actualizan sus permisos."
else
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://$TMP_DIR/trust.json" >/dev/null
  info "Rol creado."
fi
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$ROLE_NAME" \
  --policy-document "file://$TMP_DIR/policy.json"
# Session Manager: permite a SSM administrar la instancia (despliegue y consola sin SSH)
aws iam attach-role-policy --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
if ! aws iam get-instance-profile --instance-profile-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name "$ROLE_NAME" >/dev/null
  info "Instance profile creado."
fi
if [ "$(awsq iam get-instance-profile --instance-profile-name "$ROLE_NAME" --query 'length(InstanceProfile.Roles)')" = "0" ]; then
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE_NAME" --role-name "$ROLE_NAME"
fi
info "Permisos: bucket $BUCKET, parámetro $ENV_PARAM y Session Manager."


step "2/6 Configuración en Parameter Store: $ENV_PARAM"
# En la EC2 no van access keys: boto3 usa el rol de la instancia.
{
  echo "# Generado por scripts/aws_deploy_ec2.sh el $(date '+%Y-%m-%d %H:%M')"
  grep -vE '^(#|AWS_ACCESS_KEY_ID=|AWS_SECRET_ACCESS_KEY=|AWS_SESSION_TOKEN=|DEBUG=)' .env | tr -d '\r'
  echo "DEBUG=false"
} > "$TMP_DIR/env"
aws ssm put-parameter --name "$ENV_PARAM" --type SecureString --overwrite \
  --value "file://$TMP_DIR/env" >/dev/null
info "Guardada cifrada (SecureString), sin access keys y con DEBUG=false."


step "3/6 Security groups"
API_SG=$(awsq ec2 describe-security-groups \
  --filters "Name=group-name,Values=$API_SG_NAME" "Name=vpc-id,Values=$DEFAULT_VPC" \
  --query 'SecurityGroups[0].GroupId')
if [ "$API_SG" = "None" ]; then
  API_SG=$(awsq ec2 create-security-group --group-name "$API_SG_NAME" --vpc-id "$DEFAULT_VPC" \
    --description "API dev - HTTP publico" --query GroupId)
  info "Creado $API_SG_NAME: $API_SG"
else
  info "Ya existe $API_SG_NAME: $API_SG"
fi
allow_ingress "$API_SG" "API: HTTP 80 desde internet" --protocol tcp --port 80 --cidr 0.0.0.0/0
allow_ingress "$RDS_SG" "RDS: 5432 desde la API" --protocol tcp --port 5432 --source-group "$API_SG"


step "4/6 Instancia EC2: $INSTANCE_NAME ($INSTANCE_TYPE)"
read -r INSTANCE_ID INSTANCE_STATE < <(awsq ec2 describe-instances \
  --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[0].Instances[0].[InstanceId,State.Name]')
if [ "${INSTANCE_ID:-None}" != "None" ]; then
  info "Ya existe: $INSTANCE_ID (estado: $INSTANCE_STATE)"
  if [ "$INSTANCE_STATE" = "stopping" ]; then
    aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"
    INSTANCE_STATE=stopped
  fi
  if [ "$INSTANCE_STATE" = "stopped" ]; then
    aws ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null
    info "Estaba detenida; se está encendiendo."
  fi
else
  AMI_ID=$(awsq ssm get-parameter \
    --name "/aws/service/canonical/ubuntu/server/24.04/stable/current/${ARCH}/hvm/ebs-gp3/ami-id" \
    --query Parameter.Value)
  info "AMI Ubuntu 24.04 ($ARCH): $AMI_ID"
  # Un instance profile recién creado tarda unos segundos en poder usarse.
  for attempt in $(seq 1 12); do
    if out=$(awsq ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --iam-instance-profile "Name=$ROLE_NAME" \
        --security-group-ids "$API_SG" \
        --metadata-options HttpTokens=required,HttpEndpoint=enabled \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=$PROJECT},{Key=Environment,Value=dev}]" \
        --query 'Instances[0].InstanceId' 2>&1); then
      INSTANCE_ID="$out"
      break
    elif [[ "$out" == *iamInstanceProfile* || "$out" == *"Instance Profile"* ]] && [ "$attempt" -lt 12 ]; then
      info "Esperando a que el instance profile esté listo..."
      sleep 5
    else
      die "$out"
    fi
  done
  info "Creada: $INSTANCE_ID"
fi

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
read -r PUBLIC_IP PUBLIC_DNS < <(awsq ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].[PublicIpAddress,PublicDnsName]')
[ "${PUBLIC_IP:-None}" != "None" ] || die "La instancia no tiene IP pública (revisa que la subnet por defecto asigne IP pública)."
API_URL="http://${PUBLIC_DNS:-$PUBLIC_IP}"
info "Corriendo. IP pública: $PUBLIC_IP"

info "Esperando a que el agente de SSM se registre (1-3 minutos)..."
PING=""
for _ in $(seq 1 60); do
  PING=$(awsq ssm describe-instance-information \
    --filters "Key=InstanceIds,Values=$INSTANCE_ID" --query 'InstanceInformationList[0].PingStatus')
  [ "$PING" = "Online" ] && break
  sleep 5
done
[ "$PING" = "Online" ] || die "El agente de SSM no se registró. Revisa que el rol $ROLE_NAME esté asociado a la instancia y vuelve a correr el script."
info "SSM en línea."


step "5/6 Subiendo el código e instalándolo en la instancia"
tar -czf "$TMP_DIR/app.tar.gz" --exclude='__pycache__' --exclude='*.pyc' app migrations requirements.txt
aws s3 cp "$TMP_DIR/app.tar.gz" "s3://$BUCKET/_deploy/app.tar.gz" --only-show-errors
aws s3 cp scripts/ec2/deploy_remote.sh "s3://$BUCKET/_deploy/deploy_remote.sh" --only-show-errors
# URLs firmadas: la instancia descarga sin necesitar permisos sobre _deploy/
PKG_URL=$(awsq s3 presign "s3://$BUCKET/_deploy/app.tar.gz" --expires-in 900)
SCRIPT_URL=$(awsq s3 presign "s3://$BUCKET/_deploy/deploy_remote.sh" --expires-in 900)
info "Paquete subido a s3://$BUCKET/_deploy/"

cat > "$TMP_DIR/params.json" <<EOF
{
  "commands": [
    "curl -fsSL '$SCRIPT_URL' -o /tmp/nttbanca_deploy.sh && bash /tmp/nttbanca_deploy.sh '$PKG_URL' '$REGION' '$ENV_PARAM'"
  ]
}
EOF
COMMAND_ID=$(awsq ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript --comment "deploy $PROJECT api" \
  --parameters "file://$TMP_DIR/params.json" --query Command.CommandId)
info "Comando SSM: $COMMAND_ID (la primera vez tarda 3-6 minutos)"

STATUS="Pending"
printf '    '
for _ in $(seq 1 120); do
  sleep 10
  STATUS=$(awsq ssm get-command-invocation --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
    --query Status 2>/dev/null || echo Pending)
  case "$STATUS" in
    Pending|InProgress|Delayed) printf '.' ;;
    *) break ;;
  esac
done
echo
REMOTE_OUT=$(awsq ssm get-command-invocation --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
  --query StandardOutputContent)
if [ "$STATUS" != "Success" ]; then
  printf '%s\n' "$REMOTE_OUT" | tail -n 40
  awsq ssm get-command-invocation --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" \
    --query StandardErrorContent | tail -n 40
  die "El despliegue en la instancia terminó con estado: $STATUS"
fi
printf '%s\n' "$REMOTE_OUT" | grep -E '^(==>|/health|\{|Python|Migraciones|Esquema)' | sed 's/^/    /' || true


step "6/6 Probando desde tu PC: $API_URL"
for path in /health /health/db /health/s3; do
  printf '    %-11s ' "$path"
  curl -sS -m 15 "$API_URL$path" || printf '(sin respuesta)'
  echo
done


step "Listo"
cat <<EOF
    API:        $API_URL
    Swagger:    $API_URL/docs
    Instancia:  $INSTANCE_ID ($INSTANCE_TYPE, IP $PUBLIC_IP)

    Publicar cambios:  bash scripts/aws_deploy_ec2.sh
    Ver logs:          EC2 → Instances → $INSTANCE_NAME → Connect → Session Manager
                       y ahí: sudo journalctl -u nttbanca -f

    La IP cambia si detienes y vuelves a encender la instancia; el script siempre muestra la actual.
    La API no tiene autenticación: quien tenga la URL puede leer y borrar datos.
EOF
