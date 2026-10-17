# Desplegar la API en EC2

Guía para publicar el backend en una EC2 que se conecta a la RDS y al bucket creados con
[SETUP_AWS.md](SETUP_AWS.md), de modo que cualquiera pueda consumirlo y probarlo.

> Es un entorno de **desarrollo**: HTTP sin TLS y API sin autenticación. Quien tenga la URL puede leer y
> borrar datos. No lo uses con información real.

## Arquitectura

```
                    Internet
                       │ HTTP :80
                       ▼
 ┌──────────────── VPC por defecto ─────────────────────────────┐
 │                                                              │
 │  EC2 nttbanca-api-dev (Ubuntu 24.04, t4g.micro)              │
 │   └── systemd: uvicorn app.main:app :80                      │
 │        │                                                     │
 │        │ 5432 (red interna; SG de RDS acepta al SG de la API)│
 │        ▼                                                     │
 │  RDS nttbanca-dev (PostgreSQL)                               │
 └──────────────────────────────────────────────────────────────┘
        │ rol IAM de la instancia (sin access keys)
        ▼
  S3 nttbanca-dev-<cuenta>-<región>      Parameter Store /nttbanca/dev/env
   ├── uploads/   archivos de la app      (configuración cifrada: .env sin keys)
   └── _deploy/   paquete del despliegue
```

- **Sin SSH ni llaves**: el despliegue y la consola de la instancia van por AWS Systems Manager (SSM).
- **Sin access keys en el servidor**: la instancia usa el rol IAM `nttbanca-dev-api`, que solo puede usar el
  bucket y leer su parámetro de configuración.
- **Configuración**: el script toma tu `.env`, le quita las access keys, pone `DEBUG=false` y la guarda cifrada
  en Parameter Store. La instancia la descarga en cada despliegue.
- **La RDS sigue aceptando tu IP**, así que puedes seguir desarrollando en local contra la misma base.

## Requisitos

- Haber corrido [`scripts/aws_setup_dev.sh`](../scripts/aws_setup_dev.sh): RDS, bucket y `.env` completo.
- AWS CLI configurada con el usuario administrador (`aws sts get-caller-identity` debe responder).
- Git Bash en Windows (o una terminal en macOS/Linux).

## Desplegar

Desde la raíz del proyecto:

```bash
bash scripts/aws_deploy_ec2.sh
```

La primera vez tarda entre 5 y 10 minutos. El script hace, en orden:

| Paso | Qué crea o actualiza                                                                                  |
|------|--------------------------------------------------------------------------------------------------------|
| 1    | Rol IAM e instance profile `nttbanca-dev-api` (bucket, parámetro de configuración, Session Manager)   |
| 2    | Parámetro `SecureString` `/nttbanca/dev/env` con la configuración                                      |
| 3    | Security group `nttbanca-api-dev` (HTTP 80 desde internet) y regla en el SG de RDS (5432 desde la API) |
| 4    | Instancia `nttbanca-api-dev`: Ubuntu 24.04 ARM, `t4g.micro`, IMDSv2                                    |
| 5    | Sube `app/`, `migrations/` y `requirements.txt` a `s3://<bucket>/_deploy/`, aplica las migraciones y reinicia la API vía SSM |
| 6    | Prueba `/health`, `/health/db` y `/health/s3` desde tu PC                                              |

Al final muestra la URL:

```
API:        http://ec2-x-x-x-x.compute-1.amazonaws.com
Swagger:    http://ec2-x-x-x-x.compute-1.amazonaws.com/docs
```

### Publicar cambios

Vuelve a correr el mismo script. Reutiliza todo lo que ya existe, actualiza la configuración desde tu `.env`
y despliega el código nuevo (unos 2 minutos). En la instancia se guardan los últimos 3 releases en
`/opt/nttbanca/releases/`.

Se despliega lo que tengas **en tu carpeta local**, no lo que haya en GitHub.

## Operar la instancia

**Abrir una consola** (sin SSH): EC2 → Instances → `nttbanca-api-dev` → **Connect** → **Session Manager** →
Connect.

| Para                     | Comando en la consola de la instancia             |
|--------------------------|---------------------------------------------------|
| Ver logs en vivo         | `sudo journalctl -u nttbanca -f`                  |
| Últimos 100 logs         | `sudo journalctl -u nttbanca -n 100 --no-pager`   |
| Estado del servicio      | `sudo systemctl status nttbanca`                  |
| Reiniciar la API         | `sudo systemctl restart nttbanca`                 |
| Ver la configuración     | `sudo cat /opt/nttbanca/current/.env`             |

**Apagar y encender** (detenida no cobra la instancia, sí el disco):

```bash
aws ec2 stop-instances  --instance-ids <InstanceId>
aws ec2 start-instances --instance-ids <InstanceId>
```

La IP pública **cambia** al detener y volver a encender. La API arranca sola; corre de nuevo el script para
ver la URL nueva.

## Costos aproximados (us-east-1)

| Concepto                      | Precio           | Al mes (24/7) |
|-------------------------------|------------------|---------------|
| EC2 `t4g.micro`               | ~0.0084 USD/h    | ~6.15 USD     |
| IPv4 pública de la EC2        | 0.005 USD/h      | ~3.65 USD     |
| Disco EBS 8 GB gp3            | ~0.08 USD/GB-mes | ~0.65 USD     |
| Parameter Store (estándar)    | gratis           | 0             |
| **Total EC2**                 |                  | **~10.50 USD** |

Se suma a lo de RDS ([SETUP_AWS.md, sección 9](SETUP_AWS.md#9-costos-apagar-y-borrar)). Con el *Free plan* se
descuenta de los créditos; en cuentas con la capa gratuita anterior, la IPv4 de EC2 está cubierta durante el
primer año.

## Problemas frecuentes

| Síntoma                                                     | Causa probable y solución                                                                                  |
|-------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| `El agente de SSM no se registró`                           | El rol no quedó asociado o la instancia no tiene salida a internet. Vuelve a correr el script; si persiste, revisa en EC2 → la instancia → Security → IAM role. |
| El despliegue termina con estado `Failed`                   | El script imprime las últimas líneas de la instancia. Lo más común es un error en `pip install` o en la app al arrancar. |
| `/health/db` da 503 desde la EC2 pero funciona en local     | Falta la regla del SG de RDS que acepta al SG de la API (paso 3). Vuelve a correr el script.                |
| `/health/s3` da 403                                         | El bucket del `.env` no es el de la política del rol. Vuelve a correr el script tras corregir el `.env`.    |
| La URL no responde desde el navegador                       | La instancia está detenida, cambió la IP, o tu red bloquea el puerto 80. Prueba con `curl` o con otra red.  |
| `SSL validation failed ... CERTIFICATE_VERIFY_FAILED`       | Fallo pasajero de red o de un antivirus o proxy que inspecciona HTTPS. Vuelve a correr el script.            |

## Borrar el despliegue

Deja intactas la RDS y el bucket. **Esto elimina la instancia de forma irreversible:**

```bash
export MSYS_NO_PATHCONV=1   # solo en Git Bash
ID=$(aws ec2 describe-instances --filters Name=tag:Name,Values=nttbanca-api-dev \
  Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[0].Instances[0].InstanceId' --output text | tr -d '\r')
aws ec2 terminate-instances --instance-ids "$ID"
aws ec2 wait instance-terminated --instance-ids "$ID"

API_SG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=nttbanca-api-dev \
  --query 'SecurityGroups[0].GroupId' --output text | tr -d '\r')
RDS_SG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=nttbanca-rds-dev \
  --query 'SecurityGroups[0].GroupId' --output text | tr -d '\r')
aws ec2 revoke-security-group-ingress --group-id "$RDS_SG" --protocol tcp --port 5432 --source-group "$API_SG"
aws ec2 delete-security-group --group-id "$API_SG"

aws iam remove-role-from-instance-profile --instance-profile-name nttbanca-dev-api --role-name nttbanca-dev-api
aws iam delete-instance-profile --instance-profile-name nttbanca-dev-api
aws iam detach-role-policy --role-name nttbanca-dev-api \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role-policy --role-name nttbanca-dev-api --policy-name nttbanca-dev-api
aws iam delete-role --role-name nttbanca-dev-api

aws ssm delete-parameter --name /nttbanca/dev/env
aws s3 rm "s3://$(grep ^S3_BUCKET_NAME= .env | cut -d= -f2 | tr -d '\r')/_deploy/" --recursive
```

## Antes de usarlo con datos reales

- **Autenticación** en la API (API key o JWT).
- **HTTPS**: un dominio con certificado (por ejemplo Caddy en la instancia, o un balanceador con ACM).
- **RDS privada** (*Public access* en No) y sin la regla de tu IP.
- **Migraciones solo en el despliegue** (`DB_AUTO_CREATE_TABLES=false` en la app) cuando haya varias instancias.
- Para algo más robusto que una sola instancia: ECS (Fargate) detrás de un balanceador.
