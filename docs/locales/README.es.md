# Crypto AI Trading Lab

[简体中文](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/README.md) · [English](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.en.md) · [日本語](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.ja.md) · [Deutsch](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.de.md) · [Français](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.fr.md) · **Español** · [Português](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.pt.md)

Un entorno en chino para backtesting, experimentos con FreqAI y simulación de futuros. Permite comparar estrategias basadas en reglas y en modelos mediante cuentas virtuales separadas. Su alcance es la investigación y la simulación.

Python · Freqtrade · FreqAI

Un sistema independiente de simulación de contratos e investigación de criptomonedas que proporciona páginas de administración web chinas e integra Freqtrade/FreqUI, FreqAI CPU LightGBM y TradingAgents/DeepSeek. El tiempo de ejecución no depende del Codex ni de las sesiones de chat.

Actualmente, **solo admite investigación y comercio virtual; el comercio real está prohibido. Ni las estrategias ni los modelos representan una rentabilidad comprobada.**

## Función

- Cotizaciones públicas de Binance, diagnóstico de conexión, línea K y cuenta regresiva de actualización; Las cotizaciones públicas permanentes de Gate se utilizan para la simulación de contratos independientes.
- Las cuentas de contrato basadas en Binance U están vinculadas a solo lectura para consultar activos y posiciones; Las configuraciones de API se cifran y se guardan localmente.
- Tareas de investigación de TradingAgents / DeepSeek, contabilidad de uso de API, reservas de presupuesto y límites de tarifas.
- Entrenamiento de CPU FreqAI, evaluación aislada en el tiempo, guardado de modelos y validación de recarga.
- Backtesting oficial de contratos de Freqtrade y simulacro en tiempo real: posiciones largas y cortas, órdenes de apertura y cierre, estado de transacciones y pérdidas y ganancias.
- Optimización automática: genere candidatos, entrene y compare costos fuera de la muestra, cambie las versiones de simulación a través de posiciones posteriores a la venta y retroceda cuando el rendimiento se deteriore.
- Experimento de control de IA de 15 m: el grupo de reglas y el grupo de modelos FreqAI utilizan libros de contabilidad virtuales independientes para comparar señales, registros de transacciones y ganancias y pérdidas.
- Demonio de proceso independiente, desconexión, reconexión, recuperación de estado, deduplicación de pedidos, inicio y detención de Windows con un solo clic y configuración de Docker Compose.

## Windows se inicia

Para la preparación del entorno y la instalación de dependencias, consulte las instrucciones de implementación [de instalación de Windows](../../docs/INSTALL_WINDOWS.md) y [](../../docs/DEPLOYMENT.md). Requiere WSL/Ubuntu y un entorno Python compatible; Los scripts de Windows descubrirán la ruta del proyecto.

1. Clone el repositorio y prepare WSL y las dependencias de acuerdo con la documentación de instalación.
2. Haga doble clic en `启动系统.cmd` para acceder a <http://127.0.0.1:8080>.
3. Haga doble clic en `FreqUI登录信息.cmd` para ver la contraseña de administración local y desbloquear el panel en la página web.
4. Configure las API requeridas en la web, consulte precios y servicios y habilite manualmente la investigación, la capacitación o la simulación.
5. Haga doble clic en `停止系统.cmd` para detener el servicio y en `查看状态.cmd` para ver el estado de ejecución.

Cerrar el navegador o las herramientas de desarrollo no afectará los servicios en segundo plano; apagar o hibernar la computadora interrumpirá las operaciones locales. Las nuevas implementaciones no inician la simulación ni la optimización automática de forma predeterminada. El almacén no contiene la configuración, las claves, los modelos ni los datos de ejecución del desarrollador, y debe inicializarse usted mismo después de la clonación.

FreqUI de investigación oficial: <http://127.0.0.1:8081>. FreqUI de solo lectura después del inicio de la simulación original de 1 h: <http://127.0.0.1:8083>.

## Docker Compose

```sh
docker compose up -d --build
docker compose down
```

El puerto predeterminado sólo está vinculado a la máquina local. Para la primera implementación, debe configurar las credenciales y los conmutadores de módulo usted mismo. Se han proporcionado las configuraciones de imágenes del programa principal y del servicio de investigación; la compilación real de Docker y la implementación de VPS de Linux aún deben aceptarse en el entorno de destino.

## El límite entre simulación e IA

Simule el uso de fondos virtuales sin permisos de negociación de divisas. El apalancamiento actual se fija en 1x y se mantienen los límites de posición independiente, pérdida diaria, reducción y enfriamiento de pérdidas consecutivas. La estrategia se evalúa en función de la línea K de cierre. Se permite el comercio cero cuando no hay señal o no se ha liberado el control de riesgo.

La IA en el experimento controlado de 15 m se refiere al filtrado de predicción local FreqAI LightGBM; TradingAgents/DeepSeek es un proceso de investigación y optimización independiente. El modelo experimental no ha sido aceptado con fines de lucro y los resultados experimentales no reemplazarán directamente la estrategia de cuenta original. La optimización automática solo ajusta parámetros y modelos restringidos y no ejecuta código arbitrario generado por IA.

Consulte los documentos pertinentes para conocer las tarifas de gestión, la conversión de tarifas de deslizamiento, las tarifas de capital, el aislamiento de datos de capacitación y las reglas de inspección final. La conversión de costos no puede representar completamente el impacto real de la transacción y los rendimientos simulados a corto plazo no pueden probar la efectividad de la estrategia.

## Credenciales y datos operativos

Complete solo la clave API en la página web local, no la envíe a GitHub, Issue o chat. Utilice permisos de cuenta de Binance de solo lectura; Las transacciones no se ejecutarán con esta cuenta. Las llamadas de DeepSeek están sujetas a la validez de la verificación del presupuesto y del precio.

`.gitignore` excluye los archivos de entorno nativo, claves, bases de datos, modelos, registros, informes de ejecución y capturas de pantalla. El repositorio público sólo contiene código fuente, plantillas de configuración, pruebas y documentación. Los informes generados después de ejecutar el programa permanecen en la máquina local.

## Documentación

- [Implementación y recuperación de fallas](../../docs/DEPLOYMENT.md) · Guía de recuperación de [](../../docs/RECOVERY.md)
- Operación de la página web [](../../docs/WEB_CONTROLS.md) · Enlace de solo lectura de cuenta [](../../docs/BINANCE_ACCOUNT.md)
- Simulación de contrato [](../../docs/PAPER_TRADING.md) · [Experimento de control de IA de 15m](../../docs/FAST_AI_EXPERIMENT.md)
- [FreqAI CPU](../../docs/FREQAI_CPU.md) · [AI Investigación](../../docs/AI_RESEARCH.md)
- [optimiza automáticamente](../../docs/AUTOMATIC_OPTIMIZATION.md) · [política de riesgos](../../docs/RISK_POLICY.md)
- [aceptación de operación independiente](../../docs/INDEPENDENCE_ACCEPTANCE.md)

## Verificación del desarrollo

```powershell
.\scripts\lab.ps1 test
```

Primero debe instalar las dependencias en ejecución especificadas en el documento. Los scripts de aceptación de red, recuperación de antecedentes independiente y aceptación de servicios experimentales se encuentran en `scripts/`; algunos scripts requieren que se hayan iniciado los servicios locales. La salida de aceptación no se libera con el almacén.

Los upstreams utilizados por el proyecto incluyen [Freqtrade](https://github.com/freqtrade/freqtrade) y [TradingAgents](https://github.com/TauricResearch/TradingAgents). Las versiones de dependencia se fijan en el archivo de bloqueo de requisitos y el software ascendente sigue sus licencias respectivas.
