import streamlit as st
import pandas as pd
import datetime
import os
import subprocess
import threading
import time
import shutil

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

def stream_video_thread(video_path, streaming_url, row_id):
    """Thread function to stream video"""
    try:
        # Command to stream video using ffmpeg
        command = [
            'ffmpeg',
            '-re',  # Read input at native frame rate
            '-i', video_path,  # Input file
            '-c:v', 'libx264',  # Video codec
            '-preset', 'veryfast',  # Encoding preset
            '-c:a', 'aac',  # Audio codec
            '-f', 'flv',  # Output format
            streaming_url  # RTMP URL with streaming key
        ]
        
        # Start the process
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Store process ID for later reference
        with open(f"stream_{row_id}.pid", "w") as f:
            f.write(str(process.pid))
        
        # Write status file to indicate streaming has started
        with open(f"stream_{row_id}.status", "w") as f:
            f.write("streaming")
        
        # Wait for process to complete
        process.wait()
        
        # Update status file when done
        with open(f"stream_{row_id}.status", "w") as f:
            f.write("completed")
        
        # Clean up PID file
        if os.path.exists(f"stream_{row_id}.pid"):
            os.remove(f"stream_{row_id}.pid")
            
    except Exception as e:
        # Write error to status file
        with open(f"stream_{row_id}.status", "w") as f:
            f.write(f"error: {str(e)}")
        
        # Clean up PID file
        if os.path.exists(f"stream_{row_id}.pid"):
            os.remove(f"stream_{row_id}.pid")

def start_stream(video_path, streaming_url, row_id):
    """Start a stream in a separate thread"""
    # Create a thread for streaming
    thread = threading.Thread(
        target=stream_video_thread,
        args=(video_path, streaming_url, row_id)
    )
    thread.daemon = True
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
        # No PID file, assume stream is not running
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
            rtmp_url = f"{st.session_state.rtmp_server}{row['Streaming Key']}"
            start_stream(row['Video'], rtmp_url, idx)

def main():
    st.set_page_config(page_title="Live Streaming Scheduler", layout="wide")
    
    # Custom CSS
    st.markdown("""
    <style>
    .main {
        background-color: #f0f2f6;
    }
    .stButton button {
        background-color: #f0f2f6;
        color: black;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("Live Streaming Scheduler")
    
    # Check if ffmpeg is installed
    if not check_ffmpeg():
        return
    
    # Initialize session state
    if 'streams' not in st.session_state:
        st.session_state.streams = pd.DataFrame(columns=[
            'Video', 'Durasi', 'Jam Mulai', 'Streaming Key', 'Status', 'Aksi'
        ])
    
    if 'rtmp_server' not in st.session_state:
        st.session_state.rtmp_server = "rtmp://a.rtmp.youtube.com/live2/"  # Default YouTube RTMP
    
    # Check status of running streams
    check_stream_statuses()
    
    # RTMP server configuration
    with st.expander("RTMP Server Configuration"):
        rtmp_options = {
            "YouTube": "rtmp://a.rtmp.youtube.com/live2/",
            "Facebook": "rtmp://live-api-s.facebook.com:80/rtmp/",
            "Twitch": "rtmp://live.twitch.tv/app/",
            "Custom": "custom"
        }
        
        selected_service = st.selectbox(
            "Streaming Service", 
            options=list(rtmp_options.keys()),
            index=0
        )
        
        if selected_service == "Custom":
            custom_rtmp = st.text_input("Custom RTMP URL", value=st.session_state.rtmp_server)
            if custom_rtmp:
                st.session_state.rtmp_server = custom_rtmp
        else:
            st.session_state.rtmp_server = rtmp_options[selected_service]
        
        st.write(f"Current RTMP Server: {st.session_state.rtmp_server}")
    
    # Check for scheduled streams
    check_scheduled_streams()
    
    # Display the streams table with action buttons
    if not st.session_state.streams.empty:
        # Create a header row
        header_cols = st.columns([2, 1, 1, 3, 2, 2])
        header_cols[0].write("**Video**")
        header_cols[1].write("**Duration**")
        header_cols[2].write("**Start Time**")
        header_cols[3].write("**Streaming Key**")
        header_cols[4].write("**Status**")
        header_cols[5].write("**Action**")
        
        # Display each stream
        for i, row in st.session_state.streams.iterrows():
            cols = st.columns([2, 1, 1, 3, 2, 2])
            cols[0].write(os.path.basename(row['Video']))  # Just show filename
            cols[1].write(row['Durasi'])
            cols[2].write(row['Jam Mulai'])
            cols[3].write(row['Streaming Key'])
            cols[4].write(row['Status'])
            
            # Action buttons
            if row['Status'] == 'Menunggu':
                if cols[5].button("Start", key=f"start_{i}"):
                    rtmp_url = f"{st.session_state.rtmp_server}{row['Streaming Key']}"
                    if start_stream(row['Video'], rtmp_url, i):
                        st.rerun()
            
            elif row['Status'] == 'Sedang Live':
                if cols[5].button("Stop", key=f"stop_{i}"):
                    if stop_stream(i):
                        st.rerun()
            
            elif row['Status'] in ['Selesai', 'Dihentikan'] or row['Status'].startswith('error:'):
                if cols[5].button("Remove", key=f"remove_{i}"):
                    st.session_state.streams = st.session_state.streams.drop(i).reset_index(drop=True)
                    st.rerun()
        
        st.markdown("---")
    
    # Form for adding new streams
    st.subheader("Add New Stream")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        video_path = st.text_input("Video Path", placeholder="Full path to video file")
        
        # File uploader as an alternative
        uploaded_file = st.file_uploader("Or upload a video", type=['mp4', 'avi', 'mov', 'mkv'])
        if uploaded_file:
            # Save the uploaded file
            temp_dir = "temp_uploads"
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, uploaded_file.name)
            
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            video_path = temp_path
    
    with col2:
        duration = st.text_input("Duration (HH:MM:SS)", value="01:00:00")
        
        # Time picker for start time
        now = datetime.datetime.now()
        start_time = st.time_input("Start Time", value=now)
        start_time_str = start_time.strftime("%H:%M")
    
    with col3:
        streaming_key = st.text_input("Streaming Key", placeholder="Enter your streaming key")
        
        if st.button("Add Stream"):
            if video_path and streaming_key:
                # Get just the filename from the path
                video_filename = os.path.basename(video_path)
                
                new_stream = pd.DataFrame({
                    'Video': [video_path],
                    'Durasi': [duration],
                    'Jam Mulai': [start_time_str],
                    'Streaming Key': [streaming_key],
                    'Status': ['Menunggu'],
                    'Aksi': ['']
                })
                
                st.session_state.streams = pd.concat([st.session_state.streams, new_stream], ignore_index=True)
                st.success(f"Added stream for {video_filename}")
                st.rerun()
            else:
                if not video_path:
                    st.error("Please provide a video path")
                if not streaming_key:
                    st.error("Please provide a streaming key")
    
    # Instructions
    with st.expander("How to use"):
        st.markdown("""
        ### Instructions:
        
        1. **Configure RTMP Server**: Select your streaming platform (YouTube, Facebook, etc.)
        2. **Add Streams**: Provide the video path, duration, start time, and streaming key
        3. **Streaming Keys**:
           - For YouTube: Use your stream key from YouTube Studio
           - For Facebook: Use your stream key from Facebook Live Producer
           - For Twitch: Use your stream key from Twitch Dashboard
        
        ### Requirements:
        
        - FFmpeg must be installed on your system and available in PATH
        - Videos must be in a compatible format (MP4 recommended)
        - Your network must allow outbound RTMP traffic
        
        ### Notes:
        
        - Streams scheduled for a specific time will start automatically
        - You can manually start/stop streams using the action buttons
        - Multiple streams can run simultaneously, but this requires significant CPU and bandwidth
        """)

if __name__ == "__main__":
    main()
