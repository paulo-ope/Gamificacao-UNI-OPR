from __future__ import annotations


def normalize_document(value: str | None) -> str | None:
    """Reduz um CPF/CNPJ a dígitos puros - nunca salva máscara visual (`.`/`-`) no banco."""
    if value is None:
        return None
    digits = "".join(char for char in value if char.isdigit())
    return digits or None


def mask_document(value: str | None) -> str | None:
    """CPF mascarado pra exibição: só os 2 últimos dígitos ficam visíveis. Nunca devolver o CPF
    completo ao frontend - nem em tela de admin, nem no portal."""
    digits = normalize_document(value)
    if not digits:
        return None
    if len(digits) <= 4:
        return "***"
    return f"***.***.***-{digits[-2:]}"


def format_cpf_with_mask(value: str | None) -> str | None:
    """CPF com máscara completa (`XXX.XXX.XXX-XX`) - diferente de `mask_document` (que oculta a
    maior parte pra exibição), esta função devolve o CPF INTEIRO formatado, só pra uso interno do
    backend em integrações que armazenam o documento com máscara (ver
    services/ixc_collaborator_lookup.py - achado real em 2026-08-29: `funcionarios.cpf_cnpj` no
    IXC desta instalação guarda o CPF COM máscara, não só dígitos, então um filtro `=` com o valor
    normalizado não bate com o registro real). NUNCA usar o retorno disto numa resposta HTTP."""
    digits = normalize_document(value)
    if not digits or len(digits) != 11:
        return None
    return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"


def is_valid_cpf(value: str | None) -> bool:
    """Valida CPF pelo algoritmo oficial de dígito verificador (módulo 11), não só contagem de
    dígitos - `normalize_document` sozinho aceita qualquer sequência de 11 números, incluindo
    sequências óbvias como "11111111111" ou um CPF digitado errado com o dígito verificador
    inconsistente. Aceita string mascarada ou só dígitos; internamente sempre normaliza primeiro."""
    digits = normalize_document(value)
    if not digits or len(digits) != 11:
        return False
    if digits == digits[0] * 11:
        return False

    def _check_digit(base: str) -> int:
        weight = len(base) + 1
        total = sum(int(char) * (weight - index) for index, char in enumerate(base))
        remainder = (total * 10) % 11
        return 0 if remainder == 10 else remainder

    first_check = _check_digit(digits[:9])
    second_check = _check_digit(digits[:9] + str(first_check))
    return digits[-2:] == f"{first_check}{second_check}"
