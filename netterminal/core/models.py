"""Modelos de dados usados em todo o app."""
from dataclasses import dataclass

MARCAS = ["Datacom", "Huawei", "ZTE", "Fiberhome", "V-SOL", "Outra"]
PROTOCOLOS = ["SSH", "Telnet"]
GRUPO_PADRAO = "Geral"


@dataclass
class Equipamento:
    """Um ativo de rede cadastrado (ou um acesso rápido, sem cadastro).

    Repare que a senha NÃO faz parte do modelo: ela só é lida do banco no
    momento de conectar, para não ficar circulando pela interface."""
    id: object  # int (cadastrado) ou str "rapido_<ip>" (acesso rápido)
    nome: str
    ip: str
    protocolo: str
    porta: int
    grupo: str = GRUPO_PADRAO
    login_manual: bool = False
    marca: str = "Outra"
    nota: str = ""
    ssh_legado: bool = False  # aceita ssh-rsa/SHA-1 (equipamentos antigos); ver net/ssh_legado.py

    @property
    def rotulo(self):
        return f"{self.nome} ({self.ip})"

    @property
    def cadastrado(self):
        return isinstance(self.id, int)

    @classmethod
    def acesso_rapido(cls, ip, protocolo, porta):
        return cls(id=f"rapido_{ip}", nome="Acesso Rápido", ip=ip, protocolo=protocolo,
                   porta=int(porta), grupo="Acesso Rápido")


@dataclass
class Macro:
    id: int
    marca: str
    nome: str
    comando: str
