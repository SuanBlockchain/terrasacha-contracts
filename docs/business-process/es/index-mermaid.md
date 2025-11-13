# Vista General del Proceso de Negocio (Con Diagramas Mermaid)

## Introducción

La plataforma Terrasacha facilita el ciclo de vida completo de proyectos de créditos de carbono—desde la evaluación inicial de tierras hasta la tokenización y comercialización final. Este flujo de trabajo integral integra procesos tradicionales del mercado de carbono con tecnología blockchain para crear activos digitales transparentes y comercializables que representan créditos de carbono verificados.

El proceso abarca **cuatro fases principales**. Es importante destacar que la **tokenización (tokens grises) puede iniciarse temprano** con estimaciones preliminares basadas en análisis de datos e imágenes, incluso antes de la certificación formal. Esto permite financiar el proceso de certificación mismo. La **certificación ocurre una sola vez**, mientras que la **verificación es periódica** (típicamente cada 5 años) para confirmar la retención real de CO₂ y convertir tokens grises a verdes en proporción 1:1.

##Flujo de Trabajo Completo

```mermaid
flowchart LR
    A[Fase 1:<br/>Pre-Factibilidad<br/>6-18 meses] --> B[Fase 2:<br/>Certificación<br/>3-6 meses<br/>UNA VEZ]

    A -.Estimación<br/>Temprana.-> C

    C[Fase 3:<br/>Tokens Grises<br/>Recaudación] --> D[Ejecución<br/>20-30 años]

    B --> D

    D --> E[Fase 4:<br/>Verificación<br/>Cada 5 años]

    E --> F[Tokens Verdes<br/>Comercialización]

    F -.Más períodos.-> E

    style A fill:#90EE90
    style B fill:#87CEEB
    style C fill:#FFB6C1
    style E fill:#98FB98
    style F fill:#FFD700
```

---

## Las Cuatro Fases

### Fase 1: Pre-Factibilidad (Registro y Estudios)

**Duración:** 6-18 meses

Se realiza una debida diligencia exhaustiva sobre proyectos potenciales de créditos de carbono. Durante esta fase, se pueden realizar **estimaciones tempranas** usando análisis de datos e imágenes para cuantificar el potencial de captura de carbono (con incertidumbre asociada).

```mermaid
flowchart TD
    Start([Inicio]) --> Contact[Contacto Inicial<br/>Propietario + Administrador]
    Contact --> Register[Registro de Tierras]
    Register --> MOU[Firma MOU]
    MOU --> PreFeas{Estudio<br/>Pre-Factibilidad}

    PreFeas --> Legal[Análisis Legal]
    PreFeas --> Tech[Análisis Técnico<br/>+Estimación CO₂]
    PreFeas --> Fin[Análisis Financiero]

    Legal --> Report[Reporte]
    Tech --> Report
    Fin --> Report

    Report --> Viable{¿Viable?}
    Viable -->|Sí| Detailed[Factibilidad Detallada]
    Viable -->|No| Reject[Rechazado]

    Detailed --> Field[Visita de Campo]
    Field --> Final[Reporte Final]
    Final --> Phase2[A Fase 2]

    style Start fill:#90EE90
    style Phase2 fill:#87CEEB
    style Reject fill:#FFB6C1
```

**Resultado:** Determinación de viabilidad + estimación preliminar de créditos

---

### Fase 2: Certificación (PDD y Validación - Una Sola Vez)

**Duración:** 3-6 meses

El proyecto se certifica **una sola vez** mediante formulación de PDD, validación externa y registro con estándar de carbono.

```mermaid
flowchart TD
    Start([Desde Fase 1]) --> Select[Seleccionar Estándar<br/>VCS/CERCARBONO/BCR]
    Select --> PDD[Formular PDD]
    PDD --> Validator[Seleccionar<br/>Validador]
    Validator --> Desk[Desk Review]
    Desk --> Site[Visita Campo]
    Site --> Stakeh[Consulta<br/>Stakeholders]
    Stakeh --> ValRep[Reporte<br/>Validación]
    ValRep --> CAR{¿CARs?}
    CAR -->|Sí| Fix[Corregir]
    Fix --> ValRep
    CAR -->|No| Submit[Enviar a Estándar]
    Submit --> Review[Revisión]
    Review --> Reg[REGISTRADO]
    Reg --> Phase3[A Fase 3]

    style Start fill:#90EE90
    style Reg fill:#FFD700
    style Phase3 fill:#FFB6C1
```

**Resultado:** Proyecto certificado y registrado oficialmente

---

### Fase 3: Tokens Grises (Tokenización y Recaudación)

**Duración:** Puede iniciar temprano con estimaciones preliminares

Los tokens grises se acuñan basados en estimaciones tempranas para **financiar la certificación** y ejecución del proyecto.

```mermaid
flowchart TD
    Start([Desde Fase 2<br/>o Estimación Temprana]) --> Decision{¿Tokenizar?}
    Decision -->|No| Trad[Financiamiento<br/>Tradicional]
    Decision -->|Sí| Setup[Configurar<br/>Infraestructura<br/>Cardano]
    Setup --> Deploy[Desplegar<br/>Contratos<br/>Inteligentes]
    Deploy --> Config[Configurar<br/>Distribución]
    Config --> Dist[Inversionistas: 33.60%<br/>Buffer: 25.62%<br/>Certifier: 13.59%<br/>Propietario: 13.22%<br/>Admin: 12.35%<br/>Comunidad: 1.61%]
    Dist --> Mint[Acuñar<br/>Tokens Grises<br/>1:1 ton CO₂eq]
    Mint --> Market[Lanzar<br/>Marketplace]
    Market --> Fund[RECAUDACIÓN<br/>Venta a Inversionistas]
    Fund --> Fid[Cuenta<br/>Fiduciaria]
    Fid --> Exec[Ejecutar Proyecto]
    Exec --> Phase4[A Fase 4]

    style Mint fill:#FFD700
    style Phase4 fill:#98FB98
```

**Resultado:** Proyecto financiado mediante tokens grises

---

### Fase 4: Tokens Verdes (Verificación Periódica y Comercio)

**Duración:** Continua con verificaciones cada ~5 años

Verificaciones periódicas confirman CO₂ real capturado, permitiendo conversión 1:1 de tokens grises a verdes.

```mermaid
flowchart TD
    Start([Proyecto<br/>en Ejecución]) --> Monitor[Monitoreo Continuo<br/>IoT + Satélite + Campo]
    Monitor --> Period{Fin 5 años?}
    Period -->|No| Monitor
    Period -->|Sí| Report[Reporte<br/>Monitoreo]
    Report --> Calc[Calcular<br/>CO₂ Real]
    Calc --> Verif[Verificación<br/>Externa]
    Verif --> Cert[Certificación<br/>CERs Emitidos]
    Cert --> Compare{Real vs<br/>Estimado}
    Compare -->|Real menor| Buffer[Usar Buffer]
    Compare -->|Real = Est| Release[Liberar Buffer]
    Compare -->|Real mayor| Premium[Surplus]
    Buffer --> MintGreen[Acuñar<br/>Tokens Verdes<br/>SUANCO2]
    Release --> MintGreen
    Premium --> MintGreen
    MintGreen --> Redeem[Redención 1:1<br/>Gris → Verde]
    Redeem --> Trade[COMERCIALIZACIÓN]
    Trade --> Local[Mercado Local<br/>$6-7/ton]
    Trade --> Vol[Voluntario<br/>$12-25/ton]
    Trade --> Int[Internacional<br/>$30-100+/ton]
    Local --> More{¿Más<br/>períodos?}
    Vol --> More
    Int --> More
    More -->|Sí| Monitor
    More -->|No| Complete[Proyecto<br/>Completo]

    style MintGreen fill:#FFD700
    style Redeem fill:#90EE90
    style Complete fill:#87CEEB
```

**Resultado:** Créditos verificados como tokens verdes comercializables

---

## Ciclo de Vida de Tokens

```mermaid
stateDiagram-v2
    [*] --> Estimación: Análisis Datos/Imágenes

    Estimación --> TokensGrises: Acuñación<br/>Con buffer para incertidumbre

    state TokensGrises {
        [*] --> Inversionistas
        Inversionistas --> Trading: Mercado P2P
        Trading --> Inversionistas
    }

    TokensGrises --> Monitoreo: Ejecución Proyecto<br/>20-30 años

    Monitoreo --> Verificación: Cada 5 años

    Verificación --> TokensVerdes: CO₂ Real Confirmado<br/>Redención 1:1

    state TokensVerdes {
        [*] --> SUANCO2
        SUANCO2 --> Comercialización
        Comercialización --> Retiro: Offset Carbono
    }

    TokensVerdes --> [*]: Offset Reclamado
```

---

## Resumen de Línea de Tiempo

| Fase | Duración Típica | Hito Clave |
|------|----------------|-----------|
| **Fase 1: Pre-Factibilidad** | 6-18 meses | Estimación Preliminar + Reporte de Factibilidad |
| **Fase 3: Tokens Grises** | Puede iniciar temprano | Acuñación con Estimaciones Tempranas |
| **Fase 2: Certificación** | 3-6 meses | Validación y Registro (Solo Una Vez) |
| **Ejecución Continua** | 20-30 años | Implementación y Monitoreo del Proyecto |
| **Fase 4 (Período 1)** | Año 5 | Primera Verificación → Tokens Verdes |
| **Fase 4 (Período 2)** | Año 10 | Segunda Verificación → Más Tokens Verdes |
| **Fase 4 (Período N)** | Cada 5 años | Verificaciones Periódicas Continuas |

**Innovación Clave:** Los tokens grises pueden lanzarse temprano (incluso antes de certificación completa) usando estimaciones preliminares, permitiendo financiar el proceso de certificación.

**Certificación vs. Verificación:**
- **Certificación:** Una sola vez al inicio (Fase 2)
- **Verificación:** Periódica cada 5 años (Fase 4) para conversión gris→verde 1:1

---

## Opciones de Idioma

Esta documentación está disponible en:

- [**English**](../en/index.md) - View documentation in English
- **Español** (actual)

---

**Nota:** Esta es una versión con diagramas Mermaid. Para la versión con SVG originales, ver [index.md](index.md)
