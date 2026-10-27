from collections import Counter

from buscador import buscar_en_todas

productos, avisos = buscar_en_todas("audifonos")

print("Total encontrados:", len(productos))
print("Por tienda:", dict(Counter(p.tienda for p in productos)))

disponibles = [p for p in productos if p.disponible]
print("Agotados descartados:", len(productos) - len(disponibles))

print("\n10 más baratos disponibles:")
for p in sorted(disponibles, key=lambda x: x.precio)[:10]:
    print(f"{p.tienda:10} ${p.precio:>10,.0f}  {p.nombre[:45]}")

print("\nAvisos:", avisos)