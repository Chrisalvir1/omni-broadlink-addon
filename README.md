# Omni Broadlink Home Assistant Add-on Repository

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io/)

Este repositorio independiente contiene el complemento **Omni Broadlink** para Home Assistant.

## Estado de Fase 2

- El escaneo local conserva las instancias Broadlink autenticadas para no redescubrirlas en cada comando.
- Los comandos por dispositivo se serializan y los bloqueos/errores invalidan la instancia para que el siguiente intento vuelva a descubrirla.
- Se aplica un límite de espera al envío. La biblioteca de Broadlink es síncrona; el bloqueo dentro del worker mantiene serializado el dispositivo si una llamada continúa después del timeout.

Las mejoras de seguridad del PR de Fase 1 siguen siendo una dependencia separada: hasta que ese PR sea aprobado e integrado, el código de `main` no contiene aún esas protecciones.

## 📦 Instalación

1. En Home Assistant, ve a **Ajustes > Complementos > Tienda de complementos**.
2. Haz clic en los tres puntos (arriba a la derecha) > **Repositorios**.
3. Añade la URL de este repositorio: `https://github.com/Chrisalvir1/omni-broadlink-addon`
4. Busca **Omni Broadlink**, haz clic en **Instalar** y activa la opción **Mostrar en la barra lateral**.
### Seguridad de la API local

La interfaz y las rutas de control se sirven a través de Home Assistant Ingress. El complemento conserva `host_network` para detectar los dispositivos Broadlink por UDP, pero rechaza peticiones directas que no procedan de la red de Home Assistant y no devuelve los códigos IR/RF al navegador. `/api/broadlink/save` tampoco devuelve los códigos tras guardarlos.

Las respuestas de validación 422 conservan el campo y el motivo del error, pero omiten los valores recibidos para no repetir códigos o credenciales. El aprendizaje autenticado sí entrega la señal recién capturada a la UI para poder guardarla; la exportación completa solo se permite al consumidor autorizado.

## Ramas de Fase 2

La rama `codex/phase2-broadlink-resilience` incorpora reuso de sesiones BroadLink,
serialización por dispositivo y redescubrimiento tras fallos. Depende de que se
apruebe e integre primero el PR de Fase 1 de seguridad (#1); esta rama, creada
desde `main`, no incluye por sí misma esa protección de API.

La ruta `/api/export/remotes` requiere dos controles: una conexión desde `trusted_export_cidrs` y credenciales independientes para el complemento consumidor. En Opciones del complemento, configura `trusted_export_consumers` como un objeto JSON serializado en texto, con un token aleatorio de al menos 32 caracteres por consumidor. Por ejemplo: `{"omni-tuya-local":"<token-aleatorio-de-48-caracteres>"}`. El consumidor debe enviar `X-Broadlink-Consumer: omni-tuya-local` y `Authorization: Bearer <token>`; genera un secreto distinto por consumidor y guárdalo en sus opciones protegidas. No incluyas esos secretos en YAML público, automatizaciones compartidas ni logs. La ruta devuelve 401 si falta la identidad, el token no coincide o el consumidor no está configurado. Cambiar las opciones requiere reiniciar el complemento.

En instalaciones con una red de Supervisor personalizada, configura `trusted_proxy_cidrs` con la IP/CIDR del proxy de Ingress. La exportación conserva el filtro de red `trusted_export_cidrs`, pero la CIDR por sí sola ya no autoriza a leer códigos. Su valor predeterminado cubre la red local de complementos de Home Assistant; limita también ese valor a las redes necesarias. Las respuestas de listado de controles muestran nombres de comandos, pero nunca sus códigos.

### Validación ARM64 antes de desplegar

`.github/workflows/arm64-validation.yml` construye el complemento en un runner nativo `ubuntu-24.04-arm`, verifica que la imagen sea ARM64 y carga Python, la aplicación y sus dependencias compiladas sin red. No publica imágenes ni monta datos de Home Assistant. El Dockerfile usa por defecto `alpine:3.19`, la misma base declarada en `build.yaml`; Supervisor puede seguir proporcionando `BUILD_FROM`.

En un equipo ARM64 de pruebas, desde `omni-broadlink-addon/`, se puede ejecutar `docker build --platform linux/arm64 --build-arg BUILD_FROM=alpine:3.19 -t broadlink-arm64:ci .`. Un build en x86_64 necesita emulación ARM64 habilitada. Una comprobación estática del Dockerfile no confirma que las dependencias funcionen en Raspberry Pi ni que Ingress y el aprendizaje IR/RF hayan sido probados físicamente. La imagen queda pendiente hasta que el workflow y las pruebas reales pasen.
