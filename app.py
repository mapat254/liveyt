import streamlit as st
import pandas as pd
import datetime
import random
import string
import os
import subprocess
import threading
import time
import uuid

def generate_streaming_key(length=12):
    """Generate a random streaming key"""
    chars = string.ascii_lowercase + string.digits + '-'
    return ''.join(random.choice(chars) for _ in range(length))

def stream_video(video_path, streaming_url, row_id):
    """Stream a video file to RTMP server using ffmpeg"""
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
        
        # Update status to streaming
        st.session_state.streams.loc[row_id, 'Status'] = 'Sedang Live'
        st.session_state.stream_processes[row_id] = process
        
        # Wait for process to complete
        process.wait()
        
        # Update status when done
        if row_id in st.session_state.streams.index:
            st.session_state.streams.loc[row_id, 'Status'] = 'Selesai'
            if row_id in st.session_state.stream_processes:
                del st.session_state.stream_processes[row_id]
    
    except Exception as e:
        if row_id in st.session_state.streams.index:
            st.session_state.streams.loc[row_id, 'Status'] = f'Error: {str(e)}'
        if row_id in st.session_state.stream_processes:
            del st.session_state.stream_processes[row_id]

def stop_stream(row_id):
    """Stop a running stream"""
    if row_id in st.session_state.stream_processes:
        process = st.session_state.stream_processes[row_id]
        process.terminate()
        st.session_state.streams.loc[row_id, 'Status'] = 'Dihentikan'
        del st.session_state.stream_processes[row_id]

def check_scheduled_streams():
    """Check for streams that need to be started based on schedule"""
    current_time = datetime.datetime.now().strftime("%H:%M")
    
    for idx, row in st.session_state.streams.iterrows():
        if row['Status'] == 'Menunggu' and row['Jam Mulai'] == current_time:
            # Start the stream
            rtmp_url = f"{st.session_state.rtmp_server}{row['Streaming Key']}"
            thread = threading.Thread(
                target=stream_video,
                args=(row['Video'], rtmp_url, idx)
            )
            thread.daemon = True
            thread.start()

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
    
    # Initialize session state
    if 'streams' not in st.session_state:
        st.session_state.streams = pd.DataFrame(columns=[
            'Video', 'Durasi', 'Jam Mulai', 'Streaming Key', 'Status', 'Aksi'
        ])
    
    if 'stream_processes' not in st.session_state:
        st.session_state.stream_processes = {}
    
    if 'rtmp_server' not in st.session_state:
        st.session_state.rtmp_server = "rtmp://a.rtmp.youtube.com/live2/"  # Default YouTube RTMP
    
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
        for i, row in st.session_state.streams.iterrows():
            cols = st.columns([2, 1, 1, 3, 2, 2])
            cols[0].write(row['Video'])
            cols[1].write(row['Durasi'])
            cols[2].write(row['Jam Mulai'])
            cols[3].write(row['Streaming Key'])
            cols[4].write(row['Status'])
            
            # Action buttons
            if row['Status'] == 'Menunggu':
                if cols[5].button("Start", key=f"start_{i}"):
                    rtmp_url = f"{st.session_state.rtmp_server}{row['Streaming Key']}"
                    thread = threading.Thread(
                        target=stream_video,
                        args=(row['Video'], rtmp_url, i)
                    )
                    thread.daemon = True
                    thread.start()
                    st.rerun()
            
            elif row['Status'] == 'Sedang Live':
                if cols[5].button("Stop", key=f"stop_{i}"):
                    stop_stream(i)
                    st.rerun()
            
            elif row['Status'] in ['Selesai', 'Dihentikan', 'Error']:
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
        streaming_key = st.text_input("Streaming Key", value=generate_streaming_key())
        
        if st.button("Add Stream"):
            if video_path:
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
                st.error("Please provide a video path")
    
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
