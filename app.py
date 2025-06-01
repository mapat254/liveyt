import sys
import subprocess
import threading
import time
import os
import streamlit.components.v1 as components
import shutil
import datetime
import pandas as pd

# Install streamlit if not already installed
try:
    import streamlit as st
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit"])
    import streamlit as st

def check_ffmpeg():
    """Check if ffmpeg is installed and available"""
    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        st.error("FFmpeg is not installed or not in PATH. Please install FFmpeg to use this application.")
        st.markdown("""
        ### How to install FFmpeg:
        
        - **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
        - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
        - **macOS**: `brew install ffmpeg`
        """)
        return False
    return True

def run_ffmpeg(video_path, stream_key, is_shorts, row_id, log_callback=None):
    """Stream a video file to RTMP server using ffmpeg"""
    output_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
    
    # Build command with appropriate settings
    cmd = [
        "ffmpeg", 
        "-re",                  # Read input at native frame rate
        "-stream_loop", "-1",   # Loop the video indefinitely
        "-i", video_path,       # Input file
        "-c:v", "libx264",      # Video codec
        "-preset", "veryfast",  # Encoding preset
        "-b:v", "2500k",        # Video bitrate
        "-maxrate", "2500k",    # Maximum bitrate
        "-bufsize", "5000k",    # Buffer size
        "-g", "60",             # GOP size
        "-keyint_min", "60",    # Minimum GOP size
        "-c:a", "aac",          # Audio codec
        "-b:a", "128k",         # Audio bitrate
        "-f", "flv"             # Output format
    ]
    
    # Add scale filter for shorts if needed
    if is_shorts:
        cmd += ["-vf", "scale=720:1280"]
    
    # Add output URL
    cmd.append(output_url)
    
    # Log the command
    if log_callback:
        log_callback(f"Running: {' '.join(cmd)}")
    
    try:
        # Start the process
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Store process ID for later reference
        with open(f"stream_{row_id}.pid", "w") as f:
            f.write(str(process.pid))
        
        # Update status
        with open(f"stream_{row_id}.status", "w") as f:
            f.write("streaming")
        
        # Read and log output
        if log_callback:
            for line in process.stdout:
                log_callback(line.strip())
                # Also write to log file for debugging
                with open(f"stream_{row_id}.log", "a") as f:
                    f.write(line)
        
        # Wait for process to complete
        process.wait()
        
        # Update status when done
        with open(f"stream_{row_id}.status", "w") as f:
            f.write("completed")
        
        if log_callback:
            log_callback("Streaming completed.")
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        if log_callback:
            log_callback(error_msg)
        
        # Write error to status file
        with open(f"stream_{row_id}.status", "w") as f:
            f.write(f"error: {str(e)}")
    
    finally:
        if log_callback:
            log_callback("Streaming finished or stopped.")
        
        # Clean up PID file
        if os.path.exists(f"stream_{row_id}.pid"):
            os.remove(f"stream_{row_id}.pid")

def start_stream(video_path, stream_key, is_shorts, row_id):
    """Start a stream in a separate thread"""
    # Create logs list for this stream
    if 'logs' not in st.session_state:
        st.session_state.logs = {}
    
    if row_id not in st.session_state.logs:
        st.session_state.logs[row_id] = []
    
    # Define log callback function
    def log_callback(msg):
        if row_id in st.session_state.logs:
            st.session_state.logs[row_id].append(msg)
            # Keep only the last 100 log entries
            if len(st.session_state.logs[row_id]) > 100:
                st.session_state.logs[row_id] = st.session_state.logs[row_id][-100:]
    
    # Create a thread for streaming
    thread = threading.Thread(
        target=run_ffmpeg,
        args=(video_path, stream_key, is_shorts, row_id, log_callback),
        daemon=True
    )
    thread.start()
    
    # Update status immediately
    st.session_state.streams.loc[row_id, 'Status'] = 'Sedang Live'
    
    # Write initial status file
    with open(f"stream_{row_id}.status", "w") as f:
        f.write("starting")
    
    return True

def stop_stream(row_id):
    """Stop a running stream"""
    # Check if PID file exists
    if os.path.exists(f"stream_{row_id}.pid"):
        try:
            # Read the PID
            with open(f"stream_{row_id}.pid", "r") as f:
                pid = int(f.read().strip())
            
            # Try to terminate the process
            if os.name == 'nt':  # Windows
                os.system(f"taskkill /F /PID {pid}")
            else:  # Unix/Linux/Mac
                import signal
                os.kill(pid, signal.SIGTERM)
            
            # Update status
            st.session_state.streams.loc[row_id, 'Status'] = 'Dihentikan'
            
            # Update status file
            with open(f"stream_{row_id}.status", "w") as f:
                f.write("stopped")
            
            # Clean up PID file
            os.remove(f"stream_{row_id}.pid")
            
            return True
        except Exception as e:
            st.error(f"Error stopping stream: {str(e)}")
            return False
    else:
        # No PID file, try to kill all ffmpeg processes (fallback)
        if os.name == 'nt':  # Windows
            os.system("taskkill /F /IM ffmpeg.exe")
        else:  # Unix/Linux/Mac
            os.system("pkill ffmpeg")
        
        # Update status
        st.session_state.streams.loc[row_id, 'Status'] = 'Dihentikan'
        return True

def check_stream_statuses():
    """Check status files for all streams"""
    for idx, row in st.session_state.streams.iterrows():
        status_file = f"stream_{idx}.status"
        
        if os.path.exists(status_file):
            with open(status_file, "r") as f:
                status = f.read().strip()
            
            if status == "completed" and row['Status'] == 'Sedang Live':
                st.session_state.streams.loc[idx, 'Status'] = 'Selesai'
                os.remove(status_file)
            
            elif status.startswith("error:") and row['Status'] == 'Sedang Live':
                st.session_state.streams.loc[idx, 'Status'] = status
                os.remove(status_file)

def check_scheduled_streams():
    """Check for streams that need to be started based on schedule"""
    current_time = datetime.datetime.now().strftime("%H:%M")
    
    for idx, row in st.session_state.streams.iterrows():
        if row['Status'] == 'Menunggu' and row['Jam Mulai'] == current_time:
            # Start the stream
            start_stream(row['Video'], row['Streaming Key'], row.get('Is Shorts', False), idx)

def main():
    # Page configuration must be the first Streamlit command
    st.set_page_config(
        page_title="Live Streaming Scheduler",
        page_icon="📈",
        layout="wide"
    )
    
    st.title("Live Streaming Scheduler")
    
    # Check if ffmpeg is installed
    if not check_ffmpeg():
        return
    
    # Bagian iklan
    show_ads = st.sidebar.checkbox("Tampilkan Iklan", value=False)
    if show_ads:
        st.sidebar.subheader("Iklan Sponsor")
        components.html(
            """
            <div style="background:#f0f2f6;padding:20px;border-radius:10px;text-align:center">
                <script type='text/javascript' 
                        src='//pl26562103.profitableratecpm.com/28/f9/95/28f9954a1d5bbf4924abe123c76a68d2.js'>
                </script>
                <p style="color:#888">Iklan akan muncul di sini</p>
            </div>
            """,
            height=300
        )
    
    # Initialize session state
    if 'streams' not in st.session_state:
        st.session_state.streams = pd.DataFrame(columns=[
            'Video', 'Durasi', 'Jam Mulai', 'Streaming Key', 'Status', 'Is Shorts'
        ])
    
    # Check status of running streams
    check_stream_statuses()
    
    # Check for scheduled streams
    check_scheduled_streams()
    
    # Create tabs for different sections
    tab1, tab2, tab3 = st.tabs(["Stream Manager", "Add New Stream", "Logs"])
    
    with tab1:
        st.subheader("Manage Streams")
        
        # Display the streams table with action buttons
        if not st.session_state.streams.empty:
            # Create a header row
            header_cols = st.columns([2, 1, 1, 2, 2, 2])
            header_cols[0].write("**Video**")
            header_cols[1].write("**Duration**")
            header_cols[2].write("**Start Time**")
            header_cols[3].write("**Streaming Key**")
            header_cols[4].write("**Status**")
            header_cols[5].write("**Action**")
            
            # Display each stream
            for i, row in st.session_state.streams.iterrows():
                cols = st.columns([2, 1, 1, 2, 2, 2])
                cols[0].write(os.path.basename(row['Video']))  # Just show filename
                cols[1].write(row['Durasi'])
                cols[2].write(row['Jam Mulai'])
                # Mask streaming key for security
                masked_key = row['Streaming Key'][:4] + "****" if len(row['Streaming Key']) > 4 else "****"
                cols[3].write(masked_key)
                cols[4].write(row['Status'])
                
                # Action buttons
                if row['Status'] == 'Menunggu':
                    if cols[5].button("Start", key=f"start_{i}"):
                        if start_stream(row['Video'], row['Streaming Key'], row.get('Is Shorts', False), i):
                            st.rerun()
                
                elif row['Status'] == 'Sedang Live':
                    if cols[5].button("Stop", key=f"stop_{i}"):
                        if stop_stream(i):
                            st.rerun()
                
                elif row['Status'] in ['Selesai', 'Dihentikan'] or row['Status'].startswith('error:'):
                    if cols[5].button("Remove", key=f"remove_{i}"):
                        st.session_state.streams = st.session_state.streams.drop(i).reset_index(drop=True)
                        # Also remove log entries
                        if 'logs' in st.session_state and i in st.session_state.logs:
                            del st.session_state.logs[i]
                        st.rerun()
        else:
            st.info("No streams added yet. Use the 'Add New Stream' tab to add a stream.")
    
    with tab2:
        st.subheader("Add New Stream")
        
        # List available video files
        video_files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.flv', '.avi', '.mov', '.mkv'))]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("Video yang tersedia:")
            selected_video = st.selectbox("Pilih video", [""] + video_files) if video_files else None
            
            uploaded_file = st.file_uploader("Atau upload video baru", type=['mp4', 'flv', 'avi', 'mov', 'mkv'])
            
            if uploaded_file:
                # Save the uploaded file
                with open(uploaded_file.name, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.success("Video berhasil diupload!")
                video_path = uploaded_file.name
            elif selected_video:
                video_path = selected_video
            else:
                video_path = None
        
        with col2:
            stream_key = st.text_input("Stream Key", type="password")
            
            # Time picker for start time
            now = datetime.datetime.now()
            start_time = st.time_input("Start Time", value=now)
            start_time_str = start_time.strftime("%H:%M")
            
            duration = st.text_input("Duration (HH:MM:SS)", value="01:00:00")
            
            is_shorts = st.checkbox("Mode Shorts (720x1280)")
        
        if st.button("Add Stream"):
            if video_path and stream_key:
                # Get just the filename from the path
                video_filename = os.path.basename(video_path)
                
                new_stream = pd.DataFrame({
                    'Video': [video_path],
                    'Durasi': [duration],
                    'Jam Mulai': [start_time_str],
                    'Streaming Key': [stream_key],
                    'Status': ['Menunggu'],
                    'Is Shorts': [is_shorts]
                })
                
                st.session_state.streams = pd.concat([st.session_state.streams, new_stream], ignore_index=True)
                st.success(f"Added stream for {video_filename}")
                st.rerun()
            else:
                if not video_path:
                    st.error("Please provide a video path")
                if not stream_key:
                    st.error("Please provide a streaming key")
    
    with tab3:
        st.subheader("Stream Logs")
        
        # Select stream to view logs
        if 'logs' in st.session_state and st.session_state.logs:
            stream_options = {}
            for idx, row in st.session_state.streams.iterrows():
                if idx in st.session_state.logs:
                    stream_options[f"{os.path.basename(row['Video'])} (ID: {idx})"] = idx
            
            if stream_options:
                selected_stream = st.selectbox("Select stream to view logs", options=list(stream_options.keys()))
                selected_id = stream_options[selected_stream]
                
                # Display logs
                log_container = st.container()
                with log_container:
                    st.code("\n".join(st.session_state.logs[selected_id]))
                
                # Auto-refresh option
                auto_refresh = st.checkbox("Auto-refresh logs", value=True)
                if auto_refresh:
                    time.sleep(2)  # Wait 2 seconds
                    st.rerun()
            else:
                st.info("No logs available. Start a stream to see logs.")
        else:
            st.info("No logs available. Start a stream to see logs.")
    
    # Instructions
    with st.sidebar.expander("How to use"):
        st.markdown("""
        ### Instructions:
        
        1. **Add a Stream**: 
           - Select or upload a video
           - Enter your YouTube stream key
           - Set start time and duration
           - Check "Mode Shorts" for vertical videos
        
        2. **Manage Streams**:
           - Start/stop streams manually
           - Streams will start automatically at scheduled time
           - View logs to monitor streaming status
        
        ### Requirements:
        
        - FFmpeg must be installed on your system
        - Videos must be in a compatible format (MP4 recommended)
        - Your network must allow outbound RTMP traffic
        
        ### Notes:
        
        - For YouTube Shorts, use vertical videos (9:16 aspect ratio)
        - Stream keys are sensitive information - keep them private
        - Multiple streams can run simultaneously, but this requires significant CPU and bandwidth
        """)

if __name__ == '__main__':
    main()
