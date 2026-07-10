#!/usr/bin/env node
/**
 * 一键压缩 models 目录下的所有 GLB。
 * 目标：每个模型从 ~8MB 压到 <1MB。
 * 做法：纹理 WebP 1024 + 删除法线/金属度/粗糙度贴图 + 几何 weld + Draco 压缩
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SRC = 'public/assets/models';
const OUT = 'public/assets/models-optimized';

if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

// 检查依赖
try {
  require.resolve('@gltf-transform/core');
} catch {
  console.log('安装 gltf-transform...');
  execSync('npm i -D @gltf-transform/core @gltf-transform/functions @gltf-transform/extensions draco3dgltf', { stdio: 'inherit' });
}

const { NodeIO } = require('@gltf-transform/core');
const { draco, prune, dedup, weld, textureCompress } = require('@gltf-transform/functions');
const { KHRDracoMeshCompression, KHRTextureBasisu, KHRTextureTransform } = require('@gltf-transform/extensions');

const dracoEncoderPath = require.resolve('draco3dgltf');

(async () => {
  const io = new NodeIO()
    .registerExtensions([KHRDracoMeshCompression, KHRTextureBasisu, KHRTextureTransform])
    .registerDependencies({
      'draco3d.encoder': dracoEncoderPath,
    });

  const files = fs.readdirSync(SRC).filter(f => f.endsWith('.glb'));
  for (const f of files) {
    const src = path.join(SRC, f);
    const dst = path.join(OUT, f);
    console.log(`压缩 ${f} ...`);
    const doc = await io.read(src);
    await doc.transform(
      dedup(),
      prune(),
      weld(),
      draco(),
      textureCompress({ webp: { quality: 75, effort: 4 } }),
    );
    await io.write(dst, doc);
    const before = fs.statSync(src).size;
    const after = fs.statSync(dst).size;
    console.log(`  ${(before/1024/1024).toFixed(2)}MB -> ${(after/1024/1024).toFixed(2)}MB (${(100 - after/before*100).toFixed(0)}% 减小)`);
  }
  console.log('\\n完成！把 public/assets/models-optimized/ 里的文件覆盖到 public/assets/models/');
})();
