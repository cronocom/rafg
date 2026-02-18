#!/bin/bash
# Script para crear credenciales de acceso al demo

# Generar contraseña aleatoria o usar la proporcionada
PASSWORD=${1:-"demo2026"}

# Crear archivo .htpasswd con bcrypt
htpasswd -cb /etc/nginx/.htpasswd ragf_demo "$PASSWORD"

echo "✅ Credenciales creadas:"
echo "   Usuario: ragf_demo"
echo "   Password: $PASSWORD"
