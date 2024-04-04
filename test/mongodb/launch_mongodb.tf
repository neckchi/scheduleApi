resource "aws_security_group" "docdb-security-group" {
  name        = "docdb-sg"
  description = "Security group for documentdb"
  vpc_id      = "vpc-04f663e908ff9ea96"
  ingress {
    from_port   = 27017
    to_port     = 27017
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8", "10.59.44.0/24"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
# DocumentDB Cluster
resource "aws_docdb_cluster_instance" "mydocdb_instance" {
  identifier         = "docdb-cluster-instance"
  cluster_identifier = aws_docdb_cluster.docdb_cluster.id
  instance_class     = "db.t3.medium"
}
resource "aws_docdb_subnet_group" "subnet_group" {
  name       = "db-subnet-group"
  subnet_ids = ["subnet-000d8cf6eb7a43e98", "subnet-0adfd7896a832c7e0", "subnet-0475353e3420a4a8f"]
}
resource "aws_docdb_cluster" "docdb_cluster" {
  cluster_identifier      = "docdb-cluster-p2p-api-tmp"
  availability_zones      = ["eu-central-1a", "eu-central-1b", "eu-central-1c"]
  engine_version          = "4.0.0"
  master_username         = "adminuser"
  master_password         = "password123" # Replace with your own strong password
  backup_retention_period = 5             # Replace with your desired retention period
  preferred_backup_window = "07:00-09:00" # Replace with your desired backup window
  skip_final_snapshot     = true
  db_subnet_group_name    = aws_docdb_subnet_group.subnet_group.name
  vpc_security_group_ids  = [aws_security_group.docdb-security-group.id]
  storage_encrypted       = true
  # Additional cluster settings can be configured here
}
