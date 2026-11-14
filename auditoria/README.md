# Revisión inicial de mapeo EPG — 2026-11-13

Esta rama contiene el mapeo candidato de identificadores para los canales no deportivos de Zico IPTV.

- Fuente única para los canales no deportivos: XMLTV de Costa Rica descargado de EPGShare01.
- Los valores de la primera columna son los tvg-id de destino existentes en la M3U, salvo Discovery H&H: el atributo original está mal formado y se propone corregirlo a "Discovery H&H".
- No se modifican identificadores del grupo Deportes.
- La lista es una primera versión con salvedades: los programas no implican que todos los canales estén auditados en vivo.
- HBO normal, Sony Channel, History y otros casos con discrepancias o falta de verificación quedan fuera de este mapeo inicial cuando corresponde.
- La M3U privada y sus URLs no se incluyen en este repositorio.

El XML candidato de esta revisión se genera localmente a partir del archivo XMLTV aportado para auditoría. No se publica en main ni se reemplaza la EPG pública con este trabajo.
