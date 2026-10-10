# Omni Broadlink Home Assistant Add-on Repository

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io/)

Este repositorio independiente contiene el complemento **Omni Broadlink** para Home Assistant.

## 📦 Instalación

1. En Home Assistant, ve a **Ajustes > Complementos > Tienda de complementos**.
2. Haz clic en los tres puntos (arriba a la derecha) > **Repositorios**.
3. Añade la URL de este repositorio: `https://github.com/Chrisalvir1/omni-broadlink-addon`
4. Busca **Omni Broadlink**, haz clic en **Instalar** y activa la opción **Mostrar en la barra lateral**.

### Seguridad de la API local

La interfaz y las rutas de control se sirven a través de Home Assistant Ingress. El complemento conserva `host_network` para detectar los dispositivos Broadlink por UDP, pero rechaza peticiones directas que no procedan de la red de Home Assistant y no devuelve los códigos IR/RF al navegador. `/api/broadlink/save` tampoco devuelve los códigos tras guardarlos.

La ruta `/api/export/remotes` requiere dos controles: una conexión desde `trusted_export_cidrs` y credenciales independientes para el complemento consumidor. En Opciones del complemento, configura `trusted_export_consumers` como un objeto JSON serializado en texto, con un token aleatorio de al menos 32 caracteres por consumidor. Por ejemplo: `{"omni-tuya-local":"<token-aleatorio-de-48-caracteres>"}`. El consumidor debe enviar `X-Broadlink-Consumer: omni-tuya-local` y `Authorization: Bearer <token>`; genera un secreto distinto por consumidor y guárdalo en sus opciones protegidas. No incluyas esos secretos en YAML público, automatizaciones compartidas ni logs. La ruta devuelve 401 si falta la identidad, el token no coincide o el consumidor no está configurado. Cambiar las opciones requiere reiniciar el complemento.

En instalaciones con una red de Supervisor personalizada, configura `trusted_proxy_cidrs` con la IP/CIDR del proxy de Ingress. La exportación conserva el filtro de red `trusted_export_cidrs`, pero la CIDR por sí sola ya no autoriza a leer códigos. Su valor predeterminado cubre la red local de complementos de Home Assistant; limita también ese valor a las redes necesarias. Las respuestas de listado de controles muestran nombres de comandos, pero nunca sus códigos.
