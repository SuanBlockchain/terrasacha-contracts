# Diseño de Contratos Inteligentes

## Descripción de tokens

La aplicación hace uso de tokens tanto NFT como FT

### Tokens NFT

Los tokens NFT se utilizan principalmente para permitir la identificación de las UTXOs que pertenecen a la aplicación para leer información sensible almacenada en datums, principalmente en direcciones de billeteras principales y direcciones de contratos.
### Tokens FT

Existen dos tipos de tokens FT: tokens grises y tokens verdes.

- **Tokens grises**: estos son tokens que representan un porcentaje de participación en el proyecto. Son una promesa futura de créditos de carbono que serán certificados si el proyecto es exitoso. Estos tokens se crean en una proporción de 1 token/1 tonelada de CO2eq con un suministro total fijo correspondiente a la estimación inicial. La estimación tiene asociada una incertidumbre que se representa mediante una cantidad denominada _**buffer**_ para tener flexibilidad durante la realización de los certificados y mantener el equilibrio real de los créditos de carbono una vez confirmados.
- **Tokens verdes**: representan 1 tonelada de CO2eq certificada por una entidad de certificación. La entidad de certificación emite un certificado que se bloquea en el sistema y se tokeniza por la cantidad de créditos de carbono establecida en el certificado en una proporción 1:1.

---
## Descripción tipos de contratos

En cardano se pueden definir varios tipos de contrato, especificados en el campo "purpose" dentro del contexto de la transacción:

```python
ScriptPurpose = Union[Minting, Spending, Rewarding, Certifying]
```

En nuestra aplicación se van a utilizar únicamente dos, los cuales son los más comunes: de tipo "Minting" y de tipo "Spending"
### Contratos de tipo minteo
Se utilizan para crear tokens nativos y definir sus condiciones de creación o quema. En nuestra aplicación se pueden listar los siguientes:

- Para crear NFTs: usualmente crean un NFT de protocolo y un NFT de usuario siguiendo el estándar CIP68. Sirven como identificadores únicos para guardar información en datums (metadata) que los contrato de gasto pueden acceder como entrada en el proceso de validación.
- Para crear o quemar tokens grises: a nivel de proyecto, controlan la creación y quema de los FTs tokens grises.
- Para crear o quemar tokens verdes: a nivel de proyecto, controlan la creación y quema de los FTs tokens verdes.

### Contratos de tipo gasto
Se utilizan para definir reglas de validación para consumir utxos que contienen "lovelace" y/o tokens nativos, los cuales están alojados en la dirección del contrato. 

***
## Lista de contratos principales y su arquitectura

### Contrato NFT autorización protocolo (Tipo Minting)

Creación de dos tokens de autorización (referencia y usuario) siguiendo la especificación CIP68. Uno se envía a la billetera del usuario que crea el protocolo y el otro se envía a la dirección de gasto del contrato (Contrato Protocolo). El nombre del token se construye a partir de la UTXO de entrada (ID de entrada de transacción) y agregando un prefijo de la siguiente manera: REF_ para el NFT de referencia enviado al contrato, y USER_ enviado al usuario. Esto garantiza que los nombres de los tokens sean únicos y con un prefijo identificable.

- Parámetros

```python
oref: TxOutRef
```

- Redeemer

```python
@dataclass()
class Mint(PlutusData):
    CONSTR_ID = 0
@dataclass()
class Burn(PlutusData):
    CONSTR_ID = 1
```
#### Validaciones del contrato
1. Valida que el propósito del contrato sea de tipo "Minting"
2. Valida que 2 tokens sean creados o destruidos exactamente (1 reference, 1 usuario)
- Para minteo:
	1. Valida que el parámetro utxo se consuma
	2. Valida que se crea un NFT de tipo protocolo
	3. Valida que se crea un NFT de tipo usuario
- Para quema:
	1. Valida que a la salida de la transacción no existan tokens con la misma política del contrato
Este contrato puede ser utilizado libremente sin ninguna restricción. Su objetivo es generar identificadores únicos cuyos tokens, tanto referencia como usuario, sean utilizados en conjunto para desbloquear transacciones que requieran un acceso de administrador. 
### Contrato de Protocolo (Tipo Spending)

Gestiona los parámetros del protocolo para un fácil acceso en cadena. Contiene información en una UTXO, un datum sobre AdminWallet, OracleId, comisión durante la compra de tokens, listado de proyectos autorizados.

Este contrato es responsable de salvaguardar la veracidad de la información contenida en su datum, actualizarlo y eliminarlo. 

- Parámetros
```python
token_policy_id: PolicyId
```

- Redeemer
```python
@dataclass()
class UpdateProtocol(PlutusData):
    CONSTR_ID = 1
    protocol_input_index: int
    user_input_index: int
    protocol_output_index: int
@dataclass()
class EndProtocol(PlutusData):
    CONSTR_ID = 2
    protocol_input_index: int
    user_input_index: int
  
RedeemerProtocol = Union[UpdateProtocol, EndProtocol]
```

- Datum
```python
@dataclass
class DatumProtocol(PlutusData):
    CONSTR_ID = 0
    protocol_admin: List[bytes]  # List of admin public key hashes
    protocol_fee: int  # Protocol fee in lovelace
    oracle_id: bytes  # Oracle identifier
    projects: List[bytes]  # Project identifier
```

#### Validaciones del contrato
1. Valida que el propósito del contrato sea de tipo "Spending"
2. Valida que el input utilizado para encontrar el token de referencia sea el del protocolo oficial
3. Valida que el usuario que está interactuando con el contrato tenga su token de autorización
4. Valida que no se pueda utilizar más de un utxo a la vez proveniente de la dirección del contrato
- En UpdateProtocol
	1. Valida que el token no se envíe a una dirección distinta a la del contrato
	2. Valida que el datum se actualice de acuerdo a las siguientes restricciones:
		1. Los fees del protocol >= 0
		2. El número de administradores de proyectos <=10
		3. El número de proyectos gestionados por el mismo protocolo <=10
- Para EndProtocol
	1. Valida que los tokens desaparezcan al ser quemados por el contrato de quema.

#### Consideraciones generales

- Cualquier persona o entidad puede desarrollar por completo el protocol con sus tokens de validación. Sin embargo, los protocolos desplegados son completamente independientes de tal forma que los proyectos asociados en cada uno, son igualmente independientes. 
- Cualquier persona que esté en posesión del token de autorización está en la capacidad de realizar modificaciones al datum del protocolo.
- El token de referencia sirve para oficializar el utxo que tiene el datum con la información sensible del protocolo.
- El protocolo está diseñado para nunca liberar el nft de referencia de su contrato. La única salida posible es con el quemado del token y por lo tanto su fnalización. 
#### Posibles ataques

Una vez desplegado el protocolo los ataques se centran en los siguientes frentes:
1. Modificación del datum por parte de usuarios no autorizados.
2. Sacar el token de la dirección del contrato.
3. Finalizar el protocolo quemando el token.

Escenarios:
- Que alguien envíe un nft de referencia ficticio a la dirección del contrato y trate de desbloquear el nft original junto con el ficticio para modificar el datum del original. 
	- Salvaguarda: sólo un utxo de la dirección del contrato puede ser consumido a la vez en una transacción. 
- Que alguien envíe índices de redeemers falsos para validar funciones del contrato que dependen de los índices que provee el usuario en el redeemer.
	- Salvaguarda: el parámetro token_policy_id identifica el token oficial y por lo tanto todos los inputs de referencia deben contener el token oficial de acuerdo a este policy.

***
### Contrato NFT autorización proyecto

Creación de dos tokens de autorización (referencia y usuario) siguiendo la especificación CIP68. Uno se envía a la billetera del usuario que crea el proyecto y el otro se envía a la dirección de gasto del contrato (Contrato Proyecto). El nombre del token se construye a partir de la UTXO de entrada (ID de entrada de transacción) y agregando un prefijo de la siguiente manera: REF_ para el NFT de referencia enviado al contrato, y USER_ enviado al usuario. Esto garantiza que los nombres de los tokens sean únicos y con un prefijo identificable. 

Es un contrato similar al utilizado para el protocolo sin embargo tiene una validación adicional y es que los que firman la transacción para poder generar estos tokens deben estar listados en el campo project_admins del DatumProtocol.

- Parámetros
```python
oref: TxOutRef,
protocol_policy_id: PolicyId
```
- Redeemer
```python
@dataclass()
class MintProject(PlutusData):
    CONSTR_ID = 0
    protocol_input_index: int  # Index of the input UTXO to be consumed
@dataclass()
class BurnProject(PlutusData):
    CONSTR_ID = 1
    protocol_input_index: int  # Index of the reference input UTXO
```

#### Validaciones del contrato
1. Valida que el propósito del contrato sea de tipo "Minting"
2. Valida que solamente se creen dos tipos de tokens
3. Valida que el protocolo de referencia sea el correcto compárando la política del protocolo
4. Valida que el utxo del protocolo contenga el token esperado
5. Valida que quien firma la transacción haga parta de la lista de administradores en el datum del protocolo
- Para minteo:
	1. Valida que el parámetro utxo se consuma
	2. Valida que se crea un NFT de tipo protocolo
	3. Valida que se crea un NFT de tipo usuario
- Para quema:
	1. Valida que a la salida de la transacción no existan tokens con la misma política del contrato

Este contrato está atado al protocolo utilizando la política del protocolo como parámetro de inicialización. Su objetivo es generar identificadores únicos cuyos tokens, tanto referencia como usuario, deben ser utilizados en conjunto para desbloquear transacciones asociadas a actualizaciones del proyecto. A través de la validación de los administradores listados en el datum del protocolo se determina quiénes pueden crear o destruir estos certificados, y por lo tanto ser los administradores de proyectos.
### Contrato de Proyecto (tipo Spending)

Gestiona los datos y parámetros del proyecto. El datum contiene información relevante del proyecto como datos generales, así como la economía del token en cuanto a listado de participantes con sus proporciones y las reglas para su distribución.  

Este contrato es responsable de salvaguardar la veracidad de la información contenida en su datum, actualizarlo y eliminarlo. 

- Parámetros
```python
token_policy_id: PolicyId
```

- Redeemer
```python
@dataclass()
class UpdateProject(PlutusData):
    CONSTR_ID = 1
    project_input_index: int
    user_input_index: int
    project_output_index: int
@dataclass()
class UpdateToken(PlutusData):
    CONSTR_ID = 3
    project_input_index: int
    project_output_index: int
@dataclass()
class EndProject(PlutusData):
    CONSTR_ID = 2
    project_input_index: int
    user_input_index: int
    
RedeemerProject = Union[UpdateProject, UpdateToken, EndProject]
```

El redeemer cuenta fundamentalmente con 3 acciones para interactuar con el contrato.
1. **UpdateProject**: se refiere a acciones administrativas para actualizar la información del datum. Estos cambios se pueden realizar antes de que el estado del proyecto sea >=1 (distribución). A partir de este estado, se entiende que los parámetros del proyecto deben permanecer constantes durante la duración del mismo.
2. **UpdateToken**: Esta acción se utiliza en la creación y quema de tokens grises por parte de participantes identificados con una llave pública y participación definida. Valida las acciones asociadas a su economía como distribución y validación de topes permitidos para cada participante, actuando en conjunto con el contrato de tokens grises de tipo minteo. 
3. **EndProject**: acción para terminar o clausurar el proyecto.

- Datum
```python
@dataclass()
class DatumProjectParams(PlutusData):
    CONSTR_ID = 1
    project_id: bytes  # Project Identifier
    project_metadata: bytes  # Metadata URI or hash
    project_state: int  # 0=initialized, 1=distributed, 2=certified 3=closed
@dataclass()
class TokenProject(PlutusData):
    CONSTR_ID = 2
    policy_id: bytes  # Minting policy ID for the project tokens
    token_name: bytes  # Token name for the project tokens
    total_supply: int  # Total supply of tokens for the project (Grey tokens representing carbon credits promises)
@dataclass()
class StakeHolderParticipation(PlutusData):
    CONSTR_ID = 3
    stakeholder: bytes  # Stakeholder public name (investor, landowner, verifier, etc.) Investor is a keyword that do not require pkh)
    pkh: bytes  # Stakeholder public key hash
    participation: int  # Participation amount in lovelace
    claimed: bool # Whether the stakeholder has claimed their share of tokens
@dataclass()
class Certification(PlutusData):
    CONSTR_ID = 4
    certification_date: int  # Certification date as POSIX timestamp
    quantity: int  # Quantity of carbon credits certified
    real_certification_date: int  # Real certification date as POSIX timestamp (after verification)
    real_quantity: int  # Real quantity of carbon credits certified (after verification)
@dataclass()
class DatumProject(PlutusData):
    CONSTR_ID = 0
    params: DatumProjectParams
    project_token: TokenProject
    stakeholders: List[StakeHolderParticipation]  # List of stakeholders and their participation
    certifications: List[Certification]  # List of certification info for the project
```

El DatumProject es una agrupación de otros tipos de datos más complejos para la gestión y administración del token gris del proyecto:
1. params: DatumProjectParams
	1. project_id: identificador único del proyecto
	2. project_metadata: archivo de datos con información detallada del proyecto
	3. project_state: estado del proyecto (0=inicializado; 1=distribuído; 2=certificado; 3=cerrado)
2. project_token: TokenProject
	1. policy_id: política que gobierna los tokens grises
	2. token_name: nombre del token del proyecto
	3. total_supply: suministro total de tokens grises
3. stakeholders: Listado de participantes idenficados en la distribución de tokens (propietarios, administrador, socios gestores, entidad certificadora, buffer)
	1. stakeholder: Nombre identificador del participante
	2. pkh: Llave pública del participante
	3. participation: Cantidad de tokens grises del proyecto
	4. claimed: si el participante reclamó su participación
4. certifications: Listado con los periodos de certificación normalmente de periodos quinquenales.
	1. certification_date_i: fecha estimada para la certificación periodo i
	2. quantity_i: cantidad de créditos a certificar periodo i
	3. real_certification_date_i: fecha real de certificación periodo i
	4. real_quantity_i: cantidad de créditos reales certificados periodo i

#### Validaciones del contrato
1. Valida que el propósito del contrato sea de tipo "Spending"
2. Valida que el input utilizado para encontrar el token de referencia sea del proyecto oficial
3. Valida que no se pueda utilizar más de un utxo a la vez proveniente de la dirección del contrato
- En UpdateProject - Acción para actualizar el datum por parte de un administrador del contrato (billetera que contiene el token de usuario del proyecto)
	1. Valida que el usuario que está interactuando con el contrato tenga su token de autorización
	2. Valida que el token de referencia no se envíe a una dirección distinta a la del contrato
	3. Valida que el datum se actualice de acuerdo a las siguientes restricciones:
		1. El estado del proyecto, representado por un entero de 0 a 3 solamente puede aumentar, es decir, si se pasa al estado 1, no puede volver a su estado anterior.
		2. El estado del proyecto máximo es 3 ({0: "Initialized", 1: "Distributed", 2: "Certified", 3: "Closed"}).
		3. Se pueden cambiar todos los parámetros del datum si el estado del proyecto es 0 y siguiendo las siguientes reglas.
			1. Parámetros posibles de actualización:
				1. Estado del proyecto
				2. Suministro total
				3. Nombre del token gris
				4. Política del token gris
				5. Participación de los stakeholders
				6. Periodos para la certificación
			2. Restricciones:
				1. Suministro total no puede ser negativo
				2. La suma de la participación de los stakeholders debe ser menor o igual al suministro total
				3. La participación de los stakeholders no puede ser negativa
				4. El indicador de redención debe permanecer en falso durante el estado del proyecto igual a 0
				5. Los datos reales de certificación deben ser 0 mientras el estado del proyecto no haya llegado a la etapa 2 (certificación)
				6. Los datos de certificación no pueden ser negativos
				7. La suma de las cantidades de certificación debe ser igual al suministro total
		4. Si el estado del proyecto es mayor o igual a 1 todos los parámetros del proyecto se bloquean bajo esta acción del redeemer a excepción de:
			1. Parámetros posibles de actualización:
				1. Estado del proyecto
				2. Participación de los stakeholders
				3. Periodos para la certificación
			2. Restricciones:
				1. Bajo esta condición se encuentra en 1 inicialmente y puede seguir avanzando a 2 o 3 mas no disminuir
				2. Únicamente se permite actualizar el pkh de los stakeholders para que con esa llave pública puedan reclamar los tokens grises que les correspondan
				3. Únicamente se pueden cambiar los valores de fecha y cantidad real para la certificación, campos que se actualizan a medida que se van cumpliendo los hitos de certificación del proyecto. Esto es posible y ocurre únicamente cuando el estado del proyecto es igual a 1
				4. Los periodos para la certificación se mantienen constantes a partir del periodo 1. Sin embargo, a partir del periodo 2 es posible actualizar la fecha y cantidad real certificada teniendo en cuenta que no puede ser mayor a le fecha o cantidad inicialmente planeada.

- En UpdateToken - Acción para permitir la creación de tokens grises a stakeholders identificados en los campos de participación del datum del proyecto.
	1. Valida que el token de referencia no se envíe a una dirección distinta del contrato mismo
	2. Valida que el stakeholder aparezca en el listado de participantes, tenga una llave pública registrada y firme con dicha llave. 
	3. Valida que todos los campos del datum permanezcan constantes a excepción del parámetro claimed de los stakeholders.
	4. Solamente los stakeholders autorizados pueden cambiar el parametro claimed a True
- En EndProject
	1. Valida que el usuario que está interactuando con el contrato tenga su token de autorización

#### Minteo de tokens grises

El minteo de tokens grises es validado en conjunto por el contrato de Proyecto y el contrato Gris Ver [[#Contrato de token grises (tipo Minting)]].
1. El contrato de Proyecto (tipo Spending) para la validación de la actualización del datum del proyecto.
2. El contrato Gris (tipo Minting).  Para la validación de las políticas y restricciones de minteo del token gris del proyecto asociado.

Esto puede suceder en dos momentos distintos:

1. Free-minting
Bajo la acción de **UpdateProject**, cuando se pasa el proyecto del estado 0 a 1 (inicializado a distribuído), el usuario administrador del contrato proyecto debe mintear los tokens grises destinados a la comercialización en el marketplace para inversionistas. Esta transacción entonces es validada por dos contratos, en lo que se refiere a la actualización del datum del proyecto, por el contrato de proyecto, y en lo que se refiere a la cantidad de tokens y las políticas de minteo por el contrato de tokens grises del proyecto asociado.

Estos tokens grises se envían a la dirección del contrato de Inversión para custodia y comercialización. 

> [!Warning] Es mandatorio mintear los tokens grises destinados exclusivamente a los inversionistas para la venta, acción que se conoce como "free-minting". Si esta acción de minteo de tokens grises del proyecto no se realiza y el estado del proyecto pasa a 1, no será posible crear tokens grises bajo esta modalidad y únicamente estarán disponibles los tokens grises identificados dentro del listado de stakeholders.

2. Minteo por parte de stakeholders identificados en el listado
Bajo la acción de UpdateToken, los participantes identificados en el listado pueden redimir sus tokens grises en una sola operación de minteo por exactamente la cantidad total específicada. También actúan los dos contratos en conjunto, puesto que el contrato de proyecto actualiza su datum para contabilizar los participantes que ya redimieron (claimed=True). Esta acción sólo se puede realizar cuando el estado del proyecto es igual a 1.
#### Posibles ataques

Escenarios:
- Dos operaciones de minteo modificando el suministro de distintos stakeholders en la misma transacción.

### Contrato de token grises (tipo Minting)

Gestiona la creación y quema de tokens grises asociados a un proyecto utilizando como información de entrada principal la que se encuentra en el datum del proyecto, en particular la asociada a la economía del token, a su distribución y participación. 

- Parámetros
```python
project_id: PolicyId
```

- Redeemer
```python
@dataclass()
class Mint(PlutusData):
    CONSTR_ID = 0
    project_input_index: int
    project_output_index: int
@dataclass()
class Burn(PlutusData):
    CONSTR_ID = 1
```

#### Validaciones del contrato

1. Valida que el propósito del contrato sea de tipo "Minting"
2. Valida que un solo tipo de token (policyId y nombre) sea creado o destruído
3. 
- Para minteo:
	1. Valida que se exista un utxo de entrada con el datum del proyecto y que ese utxo contenga el token de referencia del proyecto.
	2. Valida que el policyId del token gris registrado en el datum del proyecto sea igual al del contrato de token grises.
	3. Valida que se esté creando el token con el nombre registrado en el datum del proyecto
	4. Valida que se creen cantidades positivas
	5. Valida el estado del proyecto para permitir acciones de minteo de la siguiente forma:
		1. Periodo **Free-minting**:
			1. El estado del proyecto debe pasar del estado 0 al 1.
			2. Valida que la cantidad a crear sea la diferencia entre el suministro total y la participación total de los stakeholders.
		2. Minteo de participantes listados:
			1. Verifica que el estado del proyecto esté en 1.
			2. Verifica que la transacción esté firmada por un participante identificado en la lista y que corresponda al pkh listado
			3. Sólo la cantidad del participante firmante es la que puede mintear.
			4. Verifica que a la salida del datum del proyecto el estado de redención (claimed) sea verdadero.
			5. Verifica que la dirección de envío de los tokens corresponda a la de la llave pública (pkh) del firmante.

