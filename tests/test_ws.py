import asyncio
import websockets
import base64
import pyaudio
import sys

# ================= CONFIGURAÇÕES =================
SERVER_URL = "wss://loginex-azure-voiceagent.1drwhc.easypanel.host/ws/audio/+5511999990001"
# Certifique-se que este número existe no seu Supabase!

# Configurações de Áudio (PCM16, 24kHz, Mono)
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000
CHUNK = 960  # 40ms de áudio
# =================================================

async def run_client():
    p = pyaudio.PyAudio()
    
    try:
        # Stream de Entrada (Microfone)
        input_stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        
        # Stream de Saída (Colunas)
        output_stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK
        )
        
        print(f"🔌 Conectando a {SERVER_URL}...")
        
        async with websockets.connect(SERVER_URL) as ws:
            print("✅ CONECTADO! Aguarde a saudação e pode falar.")
            print("   (Pressione CTRL+C para encerrar)")

            # Tarefa 1: Escutar Microfone e Enviar
            async def send_mic_audio():
                print("🎤 Microfone ativo...")
                loop = asyncio.get_event_loop()
                try:
                    while True:
                        # Ler do microfone de forma não-bloqueante
                        data = await loop.run_in_executor(None, input_stream.read, CHUNK)
                        
                        # Codificar e enviar
                        encoded = base64.b64encode(data).decode('utf-8')
                        await ws.send(encoded)
                        # Pequena pausa para não engasgar o event loop
                        await asyncio.sleep(0) 
                except Exception as e:
                    print(f"Erro no microfone: {e}")

            # Tarefa 2: Receber da Azure e Tocar (Com suporte a CLEAR_BUFFER)
            async def play_received_audio():
                print("🔊 Colunas ativas...")
                try:
                    while True:
                        message = await ws.recv()
                        
                        # === LÓGICA DE INTERRUPÇÃO (CORTE SECO) ===
                        if message == "CLEAR_BUFFER":
                            print("\n🛑 AGENTE INTERROMPIDO! (Limpando buffer local...)")
                            # Reinicia o stream para jogar fora o áudio pendente
                            output_stream.stop_stream()
                            output_stream.start_stream()
                            continue 
                        # ==========================================

                        try:
                            # Tenta decodificar áudio
                            decoded = base64.b64decode(message)
                            output_stream.write(decoded)
                        except Exception:
                            # Ignora logs de texto que não sejam comandos
                            pass
                            
                except websockets.exceptions.ConnectionClosed:
                    print("🔴 Conexão encerrada pelo servidor")

            # Rodar ambas as tarefas simultaneamente
            await asyncio.gather(send_mic_audio(), play_received_audio())

    except KeyboardInterrupt:
        print("\n👋 Encerrando...")
    finally:
        # Limpeza
        if 'input_stream' in locals():
            input_stream.stop_stream()
            input_stream.close()
        if 'output_stream' in locals():
            output_stream.stop_stream()
            output_stream.close()
        p.terminate()

if __name__ == "__main__":
    if sys.platform == 'win32':
        # Fix obrigatório para Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(run_client())