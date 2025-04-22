import mysql.connector
from typing import Tuple, Optional

def get_database_metadata(
    host: str = "127.0.0.1",
    user: str = "root",
    password: str = "Hello@123952",
    database: str = "hrms",
    port: int = 3306
) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetches both DDL statements and formatted metadata for all tables
    
    Returns:
        tuple: (ddl_statements, metadata_string) or (None, None) on failure
    """
    conn = None
    cursor = None
    try:
        # Connect to MySQL
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port
        )
        cursor = conn.cursor(dictionary=True)
        
        ddl_statements = []
        metadata_lines = []
        
        # Get all tables
        cursor.execute("SHOW TABLES")
        tables = [list(table.values())[0] for table in cursor.fetchall()]
        
        for table in tables:
            # Get DDL statement
            cursor.execute(f"SHOW CREATE TABLE `{table}`")
            create_table = cursor.fetchone()["Create Table"]
            ddl_statements.append(create_table)
            
            # Get metadata
            cursor.execute(f"DESCRIBE `{table}`")
            columns = cursor.fetchall()
            
            # Get indexes
            cursor.execute(f"SHOW INDEX FROM `{table}`")
            indexes = cursor.fetchall()
            
            # Build metadata string
            metadata_lines.append(f"=== TABLE: {table} ===")
            metadata_lines.append("COLUMNS:")
            for col in columns:
                metadata_lines.append(
                    f"  {col['Field']}: {col['Type']} "
                    f"{'PK' if col['Key'] == 'PRI' else ''}"
                    f"{'FK' if col['Key'] == 'MUL' else ''}"
                    f"{' NOT NULL' if col['Null'] == 'NO' else ''}"
                )
            
            if indexes:
                metadata_lines.append("INDEXES:")
                for idx in indexes:
                    if idx['Key_name'] != 'PRIMARY':  # Skip primary key (already shown)
                        metadata_lines.append(
                            f"  {idx['Key_name']}: {idx['Column_name']} "
                            f"({'UNIQUE' if idx['Non_unique'] == 0 else 'NON-UNIQUE'})"
                        )
            
            # Get foreign keys
            cursor.execute(f"""
                SELECT 
                    COLUMN_NAME, 
                    REFERENCED_TABLE_NAME, 
                    REFERENCED_COLUMN_NAME
                FROM 
                    INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE 
                    TABLE_SCHEMA = '{database}' AND 
                    TABLE_NAME = '{table}' AND
                    REFERENCED_TABLE_NAME IS NOT NULL
            """)
            fks = cursor.fetchall()
            
            if fks:
                metadata_lines.append("RELATIONSHIPS:")
                for fk in fks:
                    metadata_lines.append(
                        f"  {fk['COLUMN_NAME']} → "
                        f"{fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}"
                    )
            
            metadata_lines.append("")  # Empty line between tables
        
        return "\n\n".join(ddl_statements), "\n".join(metadata_lines)
        
    except mysql.connector.Error as e:
        print(f"MySQL Error [{e.errno}]: {e.msg}")
        return None, None
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return None, None
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    ddl, metadata = get_database_metadata()
    
    if ddl and metadata:
        print("=== DDL STATEMENTS ===")
        print(ddl)
        
        print("\n=== TABLE METADATA ===")
        print(metadata)
    else:
        print("Failed to fetch metadata")