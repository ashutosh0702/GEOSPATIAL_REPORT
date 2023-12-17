from fastapi import FastAPI, Depends, HTTPException, status
from mangum import Mangum
import boto3
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages 
from io import BytesIO
from fastapi.responses import StreamingResponse
from fastapi.responses import RedirectResponse
from datetime import datetime
import requests
import json
import matplotlib.dates as mdates



app = FastAPI()
handler = Mangum(app)

s3_client = boto3.client('s3', region_name='us-west-2')

@app.get("/")
def read_root():
    return {"Welcome to": "My first FastAPI deployment using Docker image"}

@app.get("/report/{farmid}/{index}")
async def read_png(farmid: int, index: str):

    bucket_name = "gis-colourized-png-data"

    objects = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f'{farmid}_')

    match_objects = [obj for obj in objects['Contents'] if obj["Key"].endswith(f"_{index.upper()}.png")]

    filtered_objects = sorted(match_objects, key=lambda x: x["Key"].split("/")[-1].split("_")[0])
    print(filtered_objects)
    print(objects)
    num_images = len(filtered_objects)

    if filtered_objects:
        farm_name = filtered_objects[0]["Key"].split("/")[0].split("_")
    print(farm_name)

    A4_WIDTH = 8.27
    A4_HEIGHT = 11.69
    SUBPLOT_WIDTH = A4_WIDTH / 5
    SUBPLOT_HEIGHT = 2.5

    cols = min(num_images,5)
    rows = (num_images + 4) // 5

    fig_width = cols * SUBPLOT_WIDTH
    fig_height = rows * SUBPLOT_HEIGHT

    fig_height = min(fig_height, A4_HEIGHT)

    fig, axs = plt.subplots(rows,cols, figsize=(fig_width, fig_height))

    if rows > 1:
        axs = [ax for sublist in axs for ax in sublist]

    elif rows==1:
        axs = [axs[i] for i in range(cols)]

    for i, obj in enumerate(filtered_objects):

        print("Inside for loop")

        key = obj["Key"]
        date = key.split("/")[1].split("_")[0]

        s3_object = s3_client.get_object(Bucket=bucket_name, Key=key)
        file_byte_string = s3_object['Body'].read()

        img = plt.imread(BytesIO(file_byte_string))
        axs[i].imshow(img)
        axs[i].set_title(date)
        axs[i].axis("off")
    
    print("Finished for loop execution")

    try:
        print("Before if-else block")
        if num_images%5 != 0:

            for j in range(num_images, rows*5):
                print(f"Turning off axis for subplot{j}")
                axs[j].axis("off")
        print("After if-else block")
    except Exception as e:
        print(e) 

    if filtered_objects:
        fig.suptitle(f"Temporal {index.upper()} for {farm_name[0]}", fontsize=16)

    fig.tight_layout()
    fig.subplots_adjust(top=0.90)


    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")

@app.get("/download/{farmid}/{index}")
async def create_report(farmid: int, index: str):
    
    bucket_name = "gis-colourized-png-data"

    objects = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f'{farmid}_')

    match_objects = [obj for obj in objects['Contents'] if obj["Key"].endswith(f"_{index.upper()}.png")]
    filtered_objects = sorted(match_objects, key=lambda x: x["Key"].split("/")[-1].split("_")[0])
    num_images = len(filtered_objects)

    if not filtered_objects:
        return {"message": "No PNG images found"}
    else:
        farm_name = filtered_objects[0]["Key"].split("/")[0].split("_")[1:]
    
    current_time = datetime.now().strftime("Report Generated at: %Y-%m-%d %H:%M")   

    pdf_buffer = BytesIO()
    with PdfPages(pdf_buffer) as pdf:
        
        fig = plt.figure(figsize=(8.27, 11.69))
        plt.text(0.5, 0.75, f"Geospatial Report for farmID : {farmid}", fontsize=24, ha='center',va='center')
        plt.text(0.5, 0.7, current_time, fontsize=12, ha='center', va='center')
        plt.axis("off")
        
        bucket='boundary-plot'
        
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=f"{farmid}_")
        
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                print(f"KEY : {key}")
                s3_object = s3_client.get_object(Bucket=bucket, Key=key)

                date_added = s3_object['ResponseMetadata']['HTTPHeaders']['last-modified']
                file_byte_string = s3_object['Body'].read()
                
                json_data = json.loads(file_byte_string.decode('utf-8'))
        
                area_value = json_data['properties']['area']
                formatted_area_value = "{:.2f}".format(float(area_value))
                # Meta data table
                table_height = 0.2
                table_data = [
                    ["Area", str(formatted_area_value)+" acres"],
                    ["Date Added on mobile application", str(date_added)]
                ]

                table_columns = ["Parameter", "Value"]

                table = plt.table(cellText=table_data, colLabels=table_columns, cellLoc='center',loc='bottom')
                table.auto_set_font_size(False)
                table.set_fontsize(10)
                table.scale(1, 1.5)
        
        pdf.savefig(fig)
        plt.close(fig)
        
        
        
        # For Plotting temporal graph
        # Make API request to get temporal graph data
        api_url = "https://tonwv78p3g.execute-api.us-west-2.amazonaws.com/test1/fmcc"
        api_params = {"farmID": farmid, "index": index}
        response = requests.get(api_url, params=api_params)

        if response.status_code != 200:
            return {"message": f"Failed to fetch temporal graph data. Status code: {response.status_code}"}

        temporal_data = response.json()
        print(temporal_data)
        # Plot temporal graph
        fig_temporal, ax_temporal = plt.subplots(figsize=(8.27, 11.69))
        fig_temporal.subplots_adjust(top=0.8, bottom=0.3, left=0.1, right=0.9)
        dates = temporal_data.get("dates", [])
        stats = temporal_data.get("stats", [])
    
        for i, stat_label in enumerate(["Mean", "Max", "Min", "Std", "Median"]):
            stat_values = [stat[i] for stat in stats]
            ax_temporal.plot(dates, stat_values, label=stat_label)
        
        # Format the x-axis to handle dates better
        ax_temporal.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax_temporal.xaxis.set_major_formatter(mdates.AutoDateFormatter(ax_temporal.xaxis.get_major_locator()))

        
        ax_temporal.set_title("Temporal Graph")
        ax_temporal.set_xlabel("Date")
        ax_temporal.set_xticklabels(dates,rotation=45)
        ax_temporal.set_ylabel("Values")
        ax_temporal.legend() 
        
        
        
        
        pdf.savefig(fig_temporal)
        
        plt.close(fig_temporal)
        
        n_plots=0
        fig,axes = create_figure_with_subplots(4)
        for i,obj in enumerate(filtered_objects, 1):
            key = obj["Key"]
            date = key.split("/")[1].split("_")[0]
            s3_object = s3_client.get_object(Bucket=bucket_name, Key=key)
            file_byte_string = s3_object['Body'].read()

            img = plt.imread(BytesIO(file_byte_string))
            #fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4 size in inches
            ax = axes[n_plots]
            ax.imshow(img)
            ax.axis('off')
            ax.set_title(date)
            # pdf.savefig(fig)
            # plt.close(fig)

            n_plots+=1
            
            if n_plots == 4 or i == len(filtered_objects):
                pdf.savefig(fig)
                plt.close(fig)
                
                if i < len(filtered_objects):
                    remaining_plots = len(filtered_objects) - i
                    n_plots_next_page = min(remaining_plots,4)
                    fig, axes = create_figure_with_subplots(n_plots_next_page)
                    n_plots=0
            
    pdf_buffer.seek(0)

    # Save PDF to S3
    pdf_key = f'reports/{farmid}_{current_time.split(":")[1]}.pdf'
    s3_client.put_object(Bucket=bucket_name, Key=pdf_key, Body=pdf_buffer.getvalue())

    # Generate a presigned URL for downloading the PDF
    presigned_url = s3_client.generate_presigned_url('get_object',
                                                     Params={'Bucket': bucket_name, 'Key': pdf_key},
                                                     ExpiresIn=3600)

    # Redirect the user to the presigned URL
    return RedirectResponse(presigned_url, status_code=status.HTTP_303_SEE_OTHER)

def create_figure_with_subplots(n_plots):
    cols=2
    if n_plots==1:
        rows=cols=1
    elif n_plots==2:
        rows=1
    else:
        rows=2
        
    fig,axes = plt.subplots(rows,cols, figsize=(8.27,11.69))
    if n_plots==1:
        axes = [axes]
    else:
        axes = axes.flatten() 
        
    return fig,axes   


  
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)