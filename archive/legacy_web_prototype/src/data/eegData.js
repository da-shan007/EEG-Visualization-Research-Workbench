export function generateSyntheticDataset() {
  const channels = ['Fp1', 'Fp2', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2'];
  const sampleRate = 250;
  const durationSeconds = 4;
  const sampleCount = sampleRate * durationSeconds;

  const series = channels.map((name, channelIndex) => {
    const values = [];
    const alpha = 10 + channelIndex * 0.3;
    const beta = 20 + channelIndex * 0.5;
    const theta = 6 + channelIndex * 0.2;

    for (let i = 0; i < sampleCount; i += 1) {
      const t = i / sampleRate;
      const alphaWave = Math.sin(2 * Math.PI * alpha * t + channelIndex) * 3.5;
      const betaWave = Math.sin(2 * Math.PI * beta * t + channelIndex * 1.3) * 2.2;
      const thetaWave = Math.sin(2 * Math.PI * theta * t + channelIndex * 0.9) * 2.7;
      const drift = Math.sin(t * 0.6 + channelIndex) * 0.8;
      const noise = (Math.random() - 0.5) * 1.4;
      values.push(alphaWave + betaWave + thetaWave + drift + noise);
    }

    return {
      name,
      values
    };
  });

  return {
    channels,
    sampleRate,
    durationSeconds,
    series
  };
}
