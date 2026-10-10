# Omni Broadlink Home Assistant Add-on Repository

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io/)

Este repositorio independiente contiene el complemento **Omni Broadlink** para Home Assistant.

## 📦 Instalación

1. En Home Assistant, ve a **Ajustes > Complementos > Tienda de complementos**.
2. Haz clic en los tres puntos (arriba a la derecha) > **Repositorios**.
3. Añade la URL de este repositorio: `https://github.com/Chrisalvir1/omni-broadlink-addon`
4. Busca **Omni Broadlink**, haz clic en **Instalar** y activa la opción **Mostrar en la barra lateral**.

### Seguridad de la API local

La interfaz y las rutas de control se sirven a través de Home Assistant Ingress. El complemento conserva `host_network` para detectar los dispositivos Broadlink por UDP, pero rechaza peticiones directas que no procedan de la red de Home Assistant y no devuelve los códigos IR/RF al navegador. La ruta `/api/export/remotes` conserva los códigos para integraciones de otros complementos y solo acepta conexiones de las redes de complementos de Home Assistant.

En instalaciones con una red de Supervisor personalizada, configura `trusted_proxy_cidrs` con la IP/CIDR del proxy de Ingress. El valor predeterminado de Home Assistant OS usa `172.30.32.2/32` para el Supervisor. La exportación entre complementos se controla por separado con `trusted_export_cidrs`; su valor predeterminado es la red local `172.30.32.0/23` de complementos de Home Assistant y comparte los códigos con cualquier complemento que pueda conectarse desde ella. Limita ambos valores a las redes estrictamente necesarias.
