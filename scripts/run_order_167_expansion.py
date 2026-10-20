"""Expansão técnica de sangria (5mm a 300 DPI) para o Pedido 167.

Aplica extensão orgânica da borda externa sem espelhar elementos internos
(linhas vermelhas, molduras ou logos) e preserva 100% do miolo em fidelidade 1:1.
"""

from pathlib import Path
from PIL import Image
import numpy as np

ORDER_DIR = Path(r"D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos\167")
TARGET_FILES = [
    "BARONESS VERSO.jpg",
    "BRIGHT VERSO.png",
    "COBRA EEL VERSO.jpg",
    "COVER GIRL VERSO.jpg",
    "GELEIA VERSO.png",
    "HYDRO-VIPER VERSO.jpg",
    "LOTSA VERSO.png",
    "SCARLETT VERSO.jpg",
]

BLEED_PX = 59  # 5mm a 300 DPI


def process_image(src_path: Path) -> dict:
    src = Image.open(src_path).convert("RGB")
    src_arr = np.array(src)
    H, W, C = src_arr.shape

    tw = W + 2 * BLEED_PX
    th = H + 2 * BLEED_PX

    # 1. Extensão de borda usando o padrão de margem externa mais externo (mode='edge')
    # Isso evita espelhar linhas internas (como molduras, logos ou linhas vermelhas)
    padded = np.pad(src_arr, ((BLEED_PX, BLEED_PX), (BLEED_PX, BLEED_PX), (0, 0)), mode="edge")

    # 2. Adiciona micro-variação orgânica/grão natural apenas nas bordas de sangria,
    # caso a borda possua textura (como o papel vintage de Bright e Lotsa)
    top_std = src_arr[0, :, :].std()
    if top_std > 1.0:
        # Grão orgânico sutil proporcional à textura nativa da borda
        rng = np.random.default_rng(42)
        grain_top = rng.normal(0, min(top_std * 0.5, 3.0), (BLEED_PX, tw, C))
        grain_bottom = rng.normal(0, min(top_std * 0.5, 3.0), (BLEED_PX, tw, C))
        grain_left = rng.normal(0, min(top_std * 0.5, 3.0), (H, BLEED_PX, C))
        grain_right = rng.normal(0, min(top_std * 0.5, 3.0), (H, BLEED_PX, C))

        padded[:BLEED_PX, :, :] = np.clip(padded[:BLEED_PX, :, :] + grain_top, 0, 255)
        padded[-BLEED_PX:, :, :] = np.clip(padded[-BLEED_PX:, :, :] + grain_bottom, 0, 255)
        padded[BLEED_PX : BLEED_PX + H, :BLEED_PX, :] = np.clip(
            padded[BLEED_PX : BLEED_PX + H, :BLEED_PX, :] + grain_left, 0, 255
        )
        padded[BLEED_PX : BLEED_PX + H, -BLEED_PX:, :] = np.clip(
            padded[BLEED_PX : BLEED_PX + H, -BLEED_PX:, :] + grain_right, 0, 255
        )

    # 3. Sobreposição 1:1 rigorosa do miolo original (garantia matemática de fidelidade absoluta)
    padded[BLEED_PX : BLEED_PX + H, BLEED_PX : BLEED_PX + W] = src_arr

    out_img = Image.fromarray(padded.astype(np.uint8))
    out_path = ORDER_DIR / f"{src_path.stem}_expanded.png"
    out_img.save(out_path, "PNG", dpi=(300, 300))

    # Validação dimensional e de miolo
    crop = out_img.crop((BLEED_PX, BLEED_PX, BLEED_PX + W, BLEED_PX + H))
    diff = float(np.mean(np.abs(np.array(crop).astype(float) - src_arr.astype(float))))

    return {
        "file": src_path.name,
        "output": out_path.name,
        "orig_size": (W, H),
        "new_size": (tw, th),
        "center_diff": diff,
        "top_mean": float(padded[:20, :, :].mean()),
        "bottom_mean": float(padded[-20:, :, :].mean()),
        "left_mean": float(padded[:, :20, :].mean()),
        "right_mean": float(padded[:, -20:, :].mean()),
    }


def main():
    print("Processando expansão técnica do Pedido 167...")
    for filename in TARGET_FILES:
        res = process_image(ORDER_DIR / filename)
        print(
            f"{res['file']:22} -> {res['output']:28} | "
            f"{res['orig_size']} -> {res['new_size']} | "
            f"Fidelidade 1:1: {res['center_diff']:.6f} | "
            f"Bordas (T,B,L,R): {res['top_mean']:.1f}, {res['bottom_mean']:.1f}, {res['left_mean']:.1f}, {res['right_mean']:.1f}"
        )


if __name__ == "__main__":
    main()
