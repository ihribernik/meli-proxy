# Desafio Meli Proxy

Mercadolibre hoy en día corre sus aplicaciones en más de 20.000 servidores, estos suelen comunicarse entre sí a través de apis, algunas accesibles desde el exterior (api.mercadolibre.com).
Uno de los problemas que tenemos actualmente es como controlar y medir estas interconexiones. Para esto necesitamos crear e implementar un "proxy de apis".

Este proxy debe poder cumplir al menos con los siguientes requisitos:

- El proxy debe poder interconectarse con los servidores de la api de mercadolibre.com
  - Ejemplo "curl 127.0.0.1:8080/categories/MLA97994" debera retornar el contenido de https://api.mercadolibre.com/categories/MLA97994 (no redirect ni cache)
- Se deberá poder controlar la cantidad máxima de llamados (rate limit) por ejemplo:
  - IP de origen 152.152.152.152 : 1000 requests por minuto
  - path /categories/\* : 10000 requests por minuto
  - IP 152.152.152.152 y path /items/\* : 10 requests por minuto
  - Otros criterios u alternativas de control son bien vistas
- La carga media del proxy (como solución) debe poder superar los 50.000 request/segundo. Por lo cual como escala la solución es muy importante.

## Extras bienvenidos:

- Estadísticas de uso: se deben almacenar (y en lo posible visualizar) estadísticas de uso del proxy
- El código debe estar en un repo git para poder pegarle un vistazo y discutir
- La interfaz para estadísticas y control podría soportar rest
- Tener todos los puntos completos (y funcionando), aunque cualquier nivel de completitud es aceptable
- Tener algún dibujo, diagrama u otros sobre como es el diseño, funcionamiento y escalabilidad del sistema suma mucho
- Funcionar contra el api de mercadolibre real, estaría buenísimo, de todas formas son conocidos algunos errores con HTTP’s, por lo que cualquier otra alternativa (mocks, otra api, etc) que pruebe el funcionamiento también es válido
