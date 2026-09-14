#!/usr/bin/env python
# coding: utf-8

# In[1]:


from pathlib import Path
from collections import Counter
import re
import zlib
import sys
import csv

# ============================================================
# CONFIGURAÇÃO
# ============================================================

ARQUIVO = "apendice_fatoracoes_Rn_sem_PRP.tex"

# Python 3.11+ limita, por padrão, conversões de inteiros muito grandes
# para strings. Aqui precisamos trabalhar com fatores de milhares de dígitos.
try:
    sys.set_int_max_str_digits(0)
except AttributeError:
    pass


# ============================================================
# FUNÇÕES ELEMENTARES
# ============================================================

def soma_digitos(n):
    return sum(int(c) for c in str(abs(n)))


def repunidade(n):
    """R_n = (10^n - 1)/9."""
    return (10**n - 1) // 9


# P(a), para a=1,...,9.
# Não há teste de primalidade aqui: são apenas os valores conhecidos.
P_A = {
    1: 0,
    2: 2,
    3: 3,
    4: 4,   # 4 = 2^2
    5: 5,
    6: 5,   # 6 = 2*3
    7: 7,
    8: 6,   # 8 = 2^3
    9: 6    # 9 = 3^2
}


# ============================================================
# ARITMÉTICA PARA Phi_n(10)
# ============================================================

def fatoracao_pequena(n):
    """
    Fatora apenas o ÍNDICE n.
    Isto NÃO é teste de primalidade dos fatores do anexo.

    Como os índices do anexo são relativamente pequenos
    (até ~10^5), divisão por tentativa é suficiente.
    """
    fatores = {}
    x = n

    while x % 2 == 0:
        fatores[2] = fatores.get(2, 0) + 1
        x //= 2

    p = 3
    while p * p <= x:
        while x % p == 0:
            fatores[p] = fatores.get(p, 0) + 1
            x //= p
        p += 2

    if x > 1:
        fatores[x] = fatores.get(x, 0) + 1

    return fatores


def divisores(n):
    fac = fatoracao_pequena(n)
    ds = [1]

    for p, e in fac.items():
        novos = []
        for d in ds:
            for k in range(e + 1):
                novos.append(d * p**k)
        ds = novos

    return ds


def mobius(n):
    """
    Função de Möbius, usada somente nos índices.
    """
    fac = fatoracao_pequena(n)

    if any(e > 1 for e in fac.values()):
        return 0

    return -1 if len(fac) % 2 else 1


_phi10_cache = {}


def phi10(n):
    """
    Calcula Phi_n(10) exatamente pela fórmula

        Phi_n(10) =
        produto_{d|n} (10^d - 1)^{mu(n/d)}.

    Não há qualquer teste de primalidade.
    """

    if n in _phi10_cache:
        return _phi10_cache[n]

    numerador = 1
    denominador = 1

    for d in divisores(n):
        mu = mobius(n // d)

        if mu == 1:
            numerador *= 10**d - 1
        elif mu == -1:
            denominador *= 10**d - 1

    q, r = divmod(numerador, denominador)

    if r != 0:
        raise ArithmeticError(
            f"Erro interno ao calcular Phi_{n}(10): divisão não exata."
        )

    _phi10_cache[n] = q
    return q


# ============================================================
# LEITURA DAS LINHAS DO ANEXO
# ============================================================

RE_LINHA = re.compile(
    r"^\s*(\d+)\s*&\s*(.*?)\\\\\s*$"
)

RE_FACTOR = re.compile(
    r"\\Rfactor\{(\d+)\}"
)

RE_FACTORPOW = re.compile(
    r"\\Rfactorpow\{(\d+)\}\{(\d+)\}"
)

RE_KCERT = re.compile(
    r"\\Kcert\{(\d+)\}\{(\d+)\}\{(\d+)\}\{(\d+)\}"
)


def extrair_linhas_fatoracao(texto):
    """
    Retorna lista (n, expressão_LaTeX).
    """
    linhas = []

    for linha in texto.splitlines():
        m = RE_LINHA.match(linha)

        if not m:
            continue

        n = int(m.group(1))
        expr = m.group(2)

        if (
            "\\Rfactor" in expr
            or "\\Kcert" in expr
            or (n == 1 and "\\(1\\)" in expr)
        ):
            linhas.append((n, expr))

    return linhas


def extrair_fatores_explicitos(expr):
    """
    Retorna Counter:
        fator -> multiplicidade
    """

    fatores = Counter()

    # Primeiro as potências
    for p, e in RE_FACTORPOW.findall(expr):
        fatores[int(p)] += int(e)

    # \Rfactor{p} não casa com \Rfactorpow, portanto não há dupla contagem
    for p in RE_FACTOR.findall(expr):
        fatores[int(p)] += 1

    return fatores


def extrair_kcert(expr):
    """
    Cada Kcert produz:
       (d, numero_de_digitos, prefixo_10, crc32)
    """
    return [
        tuple(map(int, x))
        for x in RE_KCERT.findall(expr)
    ]


# ============================================================
# RECONSTRUÇÃO DOS FATORES \Kcert
# ============================================================

def crc32_decimal(n):
    """
    CRC-32 da representação decimal, no mesmo formato usado
    pelo identificador do arquivo.
    """
    return zlib.crc32(str(n).encode("ascii")) & 0xffffffff


def reconstruir_kcert(d, ndig, prefixo, crc, fatores_explicitos):
    """
    Reconstrói o fator omitido pertencente a Phi_d(10).

    Parte de Phi_d(10) e remove todos os fatores EXPLÍCITOS
    da linha que dividem esse componente.

    No anexo atual, cada componente d possui no máximo um
    Kcert na mesma linha.
    """

    restante = phi10(d)

    # Removemos, com suas multiplicidades máximas disponíveis,
    # os fatores explícitos que realmente dividem Phi_d(10).
    for p, expoente_total in fatores_explicitos.items():

        for _ in range(expoente_total):
            if restante % p == 0:
                restante //= p
            else:
                break

    candidato = restante
    s = str(candidato)

    erros = []

    if len(s) != ndig:
        erros.append(
            f"número de dígitos: esperado {ndig}, obtido {len(s)}"
        )

    if not s.startswith(str(prefixo)):
        erros.append(
            f"prefixo: esperado {prefixo}, obtido {s[:10]}"
        )

    crc_obtido = crc32_decimal(candidato)

    if crc_obtido != crc:
        erros.append(
            f"CRC: esperado {crc}, obtido {crc_obtido}"
        )

    return candidato, erros


# ============================================================
# VERIFICAÇÃO DE UMA LINHA
# ============================================================

def verificar_linha(n, expr):

    if n == 1:
        return {
            "n": 1,
            "produto_ok": True,
            "Rn": 1,
            "P_Rn": 0,
            "fatores": Counter(),
            "kcert_erros": [],
        }

    Rn = repunidade(n)

    fatores = extrair_fatores_explicitos(expr)
    kcerts = extrair_kcert(expr)

    erros_kcert = []

    # Garantia estrutural: não queremos dois Kcert do mesmo Phi_d
    ds = [x[0] for x in kcerts]

    if len(ds) != len(set(ds)):
        raise ValueError(
            f"n={n}: aparecem dois ou mais Kcert para o mesmo Phi_d(10)."
        )

    # Reconstrói os fatores omitidos
    for d, ndig, prefixo, crc in kcerts:

        fator, erros = reconstruir_kcert(
            d,
            ndig,
            prefixo,
            crc,
            fatores
        )

        if erros:
            erros_kcert.append(
                f"Kcert d={d}: " + "; ".join(erros)
            )

        fatores[fator] += 1

    # --------------------------------------------------------
    # 1. CHECAGEM DA MULTIPLICAÇÃO
    # --------------------------------------------------------

    produto = 1

    for p, e in fatores.items():
        produto *= p**e

    produto_ok = (produto == Rn)

    # --------------------------------------------------------
    # 2. CALCULAR P(R_n)
    # --------------------------------------------------------

    P_Rn = sum(
        e * soma_digitos(p)
        for p, e in fatores.items()
    )

    return {
        "n": n,
        "Rn": Rn,
        "produto": produto,
        "produto_ok": produto_ok,
        "P_Rn": P_Rn,
        "fatores": fatores,
        "kcert_erros": erros_kcert,
        "num_kcert": len(kcerts),
    }


# ============================================================
# TESTE DA CONDIÇÃO DE SMITH
# ============================================================

def repunidade_eh_composta_segundo_fatoracao(resultado):
    """
    NÃO testa primalidade.

    Usa somente a estrutura da fatoração fornecida no anexo.

    Se R_n aparece como exatamente um único fator com expoente 1
    e esse fator é o próprio R_n, então a fatoração declara R_n
    primo e ele NÃO deve ser contado como Smith.
    """

    n = resultado["n"]

    if n == 1:
        return False

    fatores = resultado["fatores"]
    Rn = resultado["Rn"]

    if len(fatores) == 1:
        p, e = next(iter(fatores.items()))

        if e == 1 and p == Rn:
            return False

    return True


def testar_smith(resultado):

    n = resultado["n"]
    P_Rn = resultado["P_Rn"]

    encontrados = []

    for a in range(1, 10):

        # Smith exige número composto.
        if n == 1:
            composto = a in {4, 6, 8, 9}

        elif a == 1:
            composto = repunidade_eh_composta_segundo_fatoracao(
                resultado
            )

        else:
            # a > 1 e R_n > 1
            composto = True

        if not composto:
            continue

        esquerda = P_Rn + P_A[a]
        direita = a * n

        if esquerda == direita:
            encontrados.append({
                "n": n,
                "a": a,
                "P_Rn": P_Rn,
                "P_a": P_A[a],
                "soma": direita,
            })

    return encontrados


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    texto = Path(ARQUIVO).read_text(encoding="utf-8")

    linhas = extrair_linhas_fatoracao(texto)

    print("=" * 72)
    print("VERIFICAÇÃO DAS FATORAÇÕES DAS REPUNIDADES")
    print("=" * 72)
    print()
    print(f"Linhas de fatoração encontradas: {len(linhas)}")
    print()

    resultados = []
    smith = []

    erros_produto = []
    erros_kcert = []

    for contador, (n, expr) in enumerate(linhas, start=1):

        resultado = verificar_linha(n, expr)
        resultados.append(resultado)

        if not resultado["produto_ok"]:
            erros_produto.append(n)

        if resultado.get("kcert_erros"):
            erros_kcert.append(
                (n, resultado["kcert_erros"])
            )

        if resultado["produto_ok"] and not resultado.get("kcert_erros"):
            smith.extend(testar_smith(resultado))

        if contador % 25 == 0:
            print(
                f"Processados {contador:4d}/{len(linhas)} "
                f"(último n={n})"
            )

    # ========================================================
    # RESUMO
    # ========================================================

    print()
    print("=" * 72)
    print("RESUMO")
    print("=" * 72)

    print(f"Total de linhas:                 {len(resultados)}")
    print(
        "Produtos corretos:              "
        f"{sum(r['produto_ok'] for r in resultados)}"
    )
    print(f"Produtos incorretos:            {len(erros_produto)}")
    print(f"Linhas com erro em Kcert:       {len(erros_kcert)}")
    print(f"Casos Smith encontrados:        {len(smith)}")

    if erros_produto:
        print()
        print("ERROS DE MULTIPLICAÇÃO:")
        print(erros_produto)

    if erros_kcert:
        print()
        print("ERROS NOS FATORES ABREVIADOS:")
        for n, erros in erros_kcert:
            print(f"n={n}")
            for erro in erros:
                print("   ", erro)

    print()
    print("=" * 72)
    print("CASOS SMITH")
    print("=" * 72)

    for x in smith:
        n = x["n"]
        a = x["a"]

        print(
            f"a={a}, n={n}: "
            f"P(R_n)={x['P_Rn']}, "
            f"P(a)={x['P_a']}, "
            f"P(R_n)+P(a)={x['P_Rn'] + x['P_a']} = {a*n}"
        )

    # ========================================================
    # CSV 1: VERIFICAÇÃO DAS FATORAÇÕES
    # ========================================================

    with open(
        "verificacao_fatoracoes.csv",
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        w = csv.writer(f)

        w.writerow([
            "n",
            "produto_ok",
            "P_Rn",
            "numero_Kcert",
            "erro_Kcert"
        ])

        for r in resultados:
            w.writerow([
                r["n"],
                r["produto_ok"],
                r["P_Rn"],
                r.get("num_kcert", 0),
                " | ".join(r.get("kcert_erros", []))
            ])

    # ========================================================
    # CSV 2: CASOS SMITH
    # ========================================================

    with open(
        "smith_encontrados.csv",
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        w = csv.writer(f)

        w.writerow([
            "a",
            "n",
            "P_Rn",
            "P_a",
            "a_n"
        ])

        for x in smith:
            w.writerow([
                x["a"],
                x["n"],
                x["P_Rn"],
                x["P_a"],
                x["a"] * x["n"]
            ])

    print()
    print("Arquivos gerados:")
    print("  verificacao_fatoracoes.csv")
    print("  smith_encontrados.csv")


if __name__ == "__main__":
    main()

