"""GPU 전용 가상환경에서 실행되는 Z-Image-Turbo 작업자. 웹 서버를 추가로 띄우지 않는다."""

import importlib
import json
import sys
import time
from pathlib import Path


def main() -> None:
    request = json.load(sys.stdin)
    torch = importlib.import_module("torch")
    diffusion = importlib.import_module("diffusers")
    transformers = importlib.import_module("transformers")
    if not torch.cuda.is_available():
        raise RuntimeError("로컬 이미지 생성에는 Docker GPU 연결이 필요합니다.")
    started = time.monotonic()
    model = request["model"]
    # 16GB 카드에서 두 구성요소를 함께 실행하도록 가중치를 8-bit로 읽는다.
    text_encoder = transformers.Qwen3Model.from_pretrained(
        model,
        subfolder="text_encoder",
        quantization_config=transformers.BitsAndBytesConfig(load_in_8bit=True),
        torch_dtype=torch.bfloat16,
        device_map="cuda",
        local_files_only=True,
    )
    transformer = diffusion.ZImageTransformer2DModel.from_pretrained(
        model,
        subfolder="transformer",
        quantization_config=diffusion.BitsAndBytesConfig(load_in_8bit=True),
        torch_dtype=torch.bfloat16,
        device_map="cuda",
        local_files_only=True,
    )
    pipeline = diffusion.ZImagePipeline.from_pretrained(
        model,
        text_encoder=text_encoder,
        transformer=transformer,
        torch_dtype=torch.bfloat16,
        local_files_only=True,
    )
    # 양자화된 두 모델은 위에서 이미 GPU에 적재했다.
    pipeline.vae.to("cuda")
    pipeline.vae.enable_tiling()
    image = (
        pipeline(
            prompt=request["prompt"],
            width=request["width"],
            height=request["height"],
            num_inference_steps=request["steps"],
            guidance_scale=0.0,
            max_sequence_length=256,
            generator=torch.Generator("cuda").manual_seed(request["seed"]),
        )
        .images[0]
        .convert("RGB")
    )
    output = Path(request["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    for quality in (85, 75, 65, 55, 45):
        image.save(temporary, format="JPEG", quality=quality, optimize=True)
        if temporary.stat().st_size <= 93000:
            break
    if temporary.stat().st_size > 93000:
        image.thumbnail((800, 500))
        image.save(temporary, format="JPEG", quality=45, optimize=True)
    if temporary.stat().st_size > 93000:
        temporary.unlink()
        raise RuntimeError("배너 이미지 용량 제한 초과")
    temporary.replace(output)
    print(json.dumps({"seconds": round(time.monotonic() - started, 2), "output": str(output)}), flush=True)


if __name__ == "__main__":
    main()
